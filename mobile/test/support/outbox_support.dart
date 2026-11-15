import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:drift/drift.dart';
import 'package:fixflow_tech/core/api/api_client.dart';
import 'package:fixflow_tech/core/db/database.dart';
import 'package:fixflow_tech/features/outbox/outbox_models.dart';
import 'package:fixflow_tech/features/outbox/outbox_repository.dart';
import 'package:fixflow_tech/features/outbox/sync_engine.dart';

import 'fake_adapter.dart';
import 'fixtures.dart';

/// 1x1 PNG.
final tinyPng = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

File writeImage(Directory dir, String name, [List<int>? bytes]) {
  final f = File('${dir.path}/$name');
  f.writeAsBytesSync(bytes ?? tinyPng);
  return f;
}

Future<void> seedJob(
  AppDatabase db, {
  String org = 'o1',
  String id = 'r1',
  String assignmentStatus = 'ACTIVE',
  String status = 'IN_PROGRESS',
  String scope = 'active',
}) async {
  final json = assignmentJson(id: id, status: status);
  json['assignment_status'] = assignmentStatus;
  await db
      .into(db.cachedJobs)
      .insertOnConflictUpdate(
        CachedJobsCompanion.insert(
          orgId: org,
          requestId: id,
          scope: Value(scope),
          itemJson: Value(jsonEncode(json)),
          fetchedAt: DateTime.utc(2026, 11, 15, 4, 42),
        ),
      );
}

/// In-memory fake of the backend note/file endpoints with the idempotency
/// contract (201 first time, 200 identical replay, 409 reused key).
class FakeServer {
  final notes = <String, Map<String, dynamic>>{};
  final files = <String, String>{};
  int fileRequests = 0;
  int noteRequests = 0;
  int allRequests = 0;

  /// Respond to the next note POST with this status AFTER the server stored
  /// nothing (a plain rejection).
  int? rejectNoteWith;
  String rejectCode = 'e';
  String rejectMessage = 'rejected';
  int? rejectFileWith;

  /// The server stores the note and then the response is lost (timeout).
  bool dropNoteResponseOnce = false;
  bool networkDown = false;

  late final adapter = FakeAdapter(_handle);

  ResponseBody _err(int status, String code, String msg) =>
      FakeAdapter.json(status, {
        'error': {'code': code, 'message': msg},
      });

  ResponseBody _handle(RequestOptions o) {
    allRequests++;
    if (networkDown) {
      throw DioException(
        requestOptions: o,
        type: DioExceptionType.connectionError,
      );
    }
    if (o.path.endsWith('/files')) {
      fileRequests++;
      if (rejectFileWith != null) {
        return _err(rejectFileWith!, rejectCode, rejectMessage);
      }
      final fd = o.data as FormData;
      final f = {for (final e in fd.fields) e.key: e.value};
      final key = '${f['client_command_id']}:${f['client_index']}';
      final existing = files[key];
      if (existing != null) return FakeAdapter.json(200, {'id': existing});
      final id = 'file-${files.length + 1}';
      files[key] = id;
      return FakeAdapter.json(201, {'id': id});
    }
    if (o.path.endsWith('/notes')) {
      noteRequests++;
      if (rejectNoteWith != null) {
        return _err(rejectNoteWith!, rejectCode, rejectMessage);
      }
      final body = Map<String, dynamic>.from(o.data as Map);
      final key = body['client_command_id'] as String;
      final existing = notes[key];
      if (existing != null) {
        final same =
            existing['body'] == body['body'] &&
            jsonEncode(existing['attachment_ids']) ==
                jsonEncode(body['attachment_ids']);
        if (!same) {
          return _err(409, 'idempotency_key_reused', 'Key reused.');
        }
        return FakeAdapter.json(200, {'id': 'note-$key'});
      }
      notes[key] = body;
      if (dropNoteResponseOnce) {
        dropNoteResponseOnce = false;
        throw DioException(
          requestOptions: o,
          type: DioExceptionType.receiveTimeout,
        );
      }
      return FakeAdapter.json(201, {'id': 'note-$key'});
    }
    return _err(404, 'not_found', 'nope');
  }
}

class Rig {
  Rig._(this.db, this.dir, this.repo, this.server, this.engine, this.clock);

  final AppDatabase db;
  final Directory dir;
  final OutboxRepository repo;
  final FakeServer server;
  final OutboxSyncEngine engine;
  final TestClock clock;

  static Rig create(
    AppDatabase db, {
    Directory? dir,
    String? user = 'u1',
    String? org = 'o1',
    bool Function()? canSync,
  }) {
    final d = dir ?? Directory.systemTemp.createTempSync('ff_outbox_');
    final clock = TestClock();
    final repo = OutboxRepository(db, () async => d, clock: clock.now);
    final server = FakeServer();
    final api = ApiClient(
      ApiClient.buildDio(
        baseUrl: 'http://fake',
        authContext: () => (token: 't', orgId: org),
        adapter: server.adapter,
      ),
    );
    final engine = OutboxSyncEngine(
      repo: repo,
      api: api,
      canSync: canSync ?? () => true,
      userId: () => user,
      orgId: () => org,
      clock: clock.now,
    );
    return Rig._(db, d, repo, server, engine, clock);
  }

  Future<OutboxItem> enqueue({
    String body = 'Replaced the lamp',
    int photos = 0,
    String user = 'u1',
    String request = 'r1',
  }) async {
    final imgs = [
      for (var i = 0; i < photos; i++)
        PickedImage(path: writeImage(dir, 'in$i.png').path, name: 'in$i.png'),
    ];
    return repo.enqueueNote(
      orgId: 'o1',
      userId: user,
      requestId: request,
      body: body,
      images: imgs,
    );
  }

  void dispose() {
    if (dir.existsSync()) dir.deleteSync(recursive: true);
  }
}

class TestClock {
  DateTime current = DateTime.utc(2026, 11, 15, 4, 42);
  DateTime now() => current;
}

extension RigClock on Rig {
  void advance(Duration d) => clock.current = clock.current.add(d);
}
