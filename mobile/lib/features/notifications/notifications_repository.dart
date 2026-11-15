import '../../core/api/api_client.dart';

/// One in-app notification (COMM-03).
class NotificationItem {
  const NotificationItem({
    required this.id,
    required this.type,
    required this.title,
    required this.body,
    this.requestId,
    this.readAt,
    required this.createdAt,
  });

  factory NotificationItem.fromJson(Map<String, dynamic> j) => NotificationItem(
    id: j['id'] as String,
    type: (j['type'] ?? '') as String,
    title: (j['title'] ?? '') as String,
    body: (j['body'] ?? '') as String,
    requestId: j['request_id'] as String?,
    readAt: j['read_at'] is String
        ? DateTime.tryParse(j['read_at'] as String)
        : null,
    createdAt: j['created_at'] is String
        ? (DateTime.tryParse(j['created_at'] as String) ?? DateTime.now())
        : DateTime.now(),
  );

  final String id;
  final String type;
  final String title;
  final String body;
  final String? requestId;
  final DateTime? readAt;
  final DateTime createdAt;

  bool get unread => readAt == null;

  NotificationItem asRead(DateTime at) => NotificationItem(
    id: id,
    type: type,
    title: title,
    body: body,
    requestId: requestId,
    readAt: readAt ?? at,
    createdAt: createdAt,
  );
}

abstract class NotificationsRepository {
  /// Newest first (server order).
  Future<List<NotificationItem>> list({int pageSize = 50});
  Future<int> unreadCount();
  Future<NotificationItem> markRead(String id);
  Future<void> markAllRead();
}

class ApiNotificationsRepository implements NotificationsRepository {
  ApiNotificationsRepository(this._api);
  final ApiClient _api;

  @override
  Future<List<NotificationItem>> list({int pageSize = 50}) async {
    final json = await _api.getJson(
      '/notifications',
      query: {'page': 1, 'page_size': pageSize},
    );
    return [
      for (final i in (json['items'] as List? ?? const []))
        NotificationItem.fromJson((i as Map).cast<String, dynamic>()),
    ];
  }

  @override
  Future<int> unreadCount() async =>
      ((await _api.getJson('/notifications/unread-count'))['unread'] as num?)
          ?.toInt() ??
      0;

  @override
  Future<NotificationItem> markRead(String id) async =>
      NotificationItem.fromJson(await _api.postJson('/notifications/$id/read'));

  @override
  Future<void> markAllRead() async {
    await _api.postJson('/notifications/read-all');
  }
}
