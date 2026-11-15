import 'dart:io';

import 'package:dio/dio.dart';
import 'package:path/path.dart' as p;

import '../../core/api/api_client.dart';
import '../outbox/outbox_repository.dart' show sniffImage;

/// Active inventory item the technician can consume.
class InventoryItem {
  const InventoryItem({
    required this.id,
    required this.code,
    required this.name,
    required this.unit,
    required this.stock,
  });

  factory InventoryItem.fromJson(Map<String, dynamic> j) => InventoryItem(
    id: j['id'] as String,
    code: (j['code'] ?? '') as String,
    name: (j['name'] ?? '') as String,
    unit: (j['unit'] ?? '') as String,
    stock: (j['stock_quantity'] ?? '0').toString(),
  );

  final String id;
  final String code;
  final String name;
  final String unit;
  final String stock;
}

/// One recorded material usage of a job.
class MaterialRecord {
  const MaterialRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.unit,
    required this.quantity,
    required this.clientCommandId,
    this.createdAt,
  });

  factory MaterialRecord.fromJson(Map<String, dynamic> j) {
    final item = (j['item'] as Map?)?.cast<String, dynamic>() ?? const {};
    return MaterialRecord(
      id: (j['id'] ?? '') as String,
      code: (item['code'] ?? '') as String,
      name: (item['name'] ?? 'Material') as String,
      unit: (item['unit'] ?? '') as String,
      quantity: (j['quantity'] ?? '').toString(),
      clientCommandId: (j['client_command_id'] ?? '') as String,
      createdAt: j['created_at'] is String
          ? DateTime.tryParse(j['created_at'] as String)
          : null,
    );
  }

  final String id;
  final String code;
  final String name;
  final String unit;
  final String quantity;
  final String clientCommandId;
  final DateTime? createdAt;
}

/// Online-only technician actions (MOB-08). Implementations throw only
/// `AppException`s; nothing here is ever faked locally.
abstract class JobActionsRepository {
  Future<void> accept(String requestId);
  Future<void> decline(String requestId, String reason);
  Future<void> start(String requestId);
  Future<void> block(String requestId, String reason);
  Future<void> resume(String requestId, String note);
  Future<void> complete(String requestId, String note);

  /// Uploads one COMPLETION photo. Re-sending the same [commandId]+[index]
  /// is replay-safe (server answers 200 with the same file). Returns file id.
  Future<String> uploadCompletionPhoto(
    String requestId, {
    required String path,
    required String commandId,
    required int index,
  });

  Future<List<InventoryItem>> inventory();

  /// Replay-safe through [commandId] (201 first time, 200 replay).
  Future<MaterialRecord> consumeMaterial(
    String requestId, {
    required String commandId,
    required String itemId,
    required String quantity,
  });
}

class ApiJobActionsRepository implements JobActionsRepository {
  ApiJobActionsRepository(this._api);
  final ApiClient _api;

  String _p(String id, String action) => '/requests/$id/$action';

  @override
  Future<void> accept(String id) => _api.postJson(_p(id, 'accept'));

  @override
  Future<void> decline(String id, String reason) =>
      _api.postJson(_p(id, 'decline'), body: {'reason': reason});

  @override
  Future<void> start(String id) => _api.postJson(_p(id, 'start'));

  @override
  Future<void> block(String id, String reason) =>
      _api.postJson(_p(id, 'block'), body: {'reason': reason});

  @override
  Future<void> resume(String id, String note) =>
      _api.postJson(_p(id, 'resume'), body: {'note': note});

  @override
  Future<void> complete(String id, String note) =>
      _api.postJson(_p(id, 'complete'), body: {'note': note});

  @override
  Future<String> uploadCompletionPhoto(
    String requestId, {
    required String path,
    required String commandId,
    required int index,
  }) async {
    final head = await _readHead(path);
    final mime = sniffImage(head)?.mime ?? 'image/jpeg';
    final form = FormData.fromMap({
      'purpose': 'COMPLETION',
      'client_command_id': commandId,
      'client_index': index,
      'file': await MultipartFile.fromFile(
        path,
        filename: p.basename(path),
        contentType: DioMediaType.parse(mime),
      ),
    });
    final json = await _api.postForm(_p(requestId, 'files'), form);
    return json['id'] as String;
  }

  Future<List<int>> _readHead(String path) async {
    final raf = await File(path).open();
    try {
      return await raf.read(16);
    } finally {
      await raf.close();
    }
  }

  @override
  Future<List<InventoryItem>> inventory() async {
    final json = await _api.getJson('/inventory');
    return [
      for (final i in (json['items'] as List? ?? const []))
        InventoryItem.fromJson((i as Map).cast<String, dynamic>()),
    ];
  }

  @override
  Future<MaterialRecord> consumeMaterial(
    String requestId, {
    required String commandId,
    required String itemId,
    required String quantity,
  }) async => MaterialRecord.fromJson(
    await _api.postJson(
      _p(requestId, 'materials'),
      body: {
        'client_command_id': commandId,
        'item_id': itemId,
        'quantity': quantity,
      },
    ),
  );
}
