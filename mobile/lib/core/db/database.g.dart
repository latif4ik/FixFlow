// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'database.dart';

// ignore_for_file: type=lint
class $SessionTableTable extends SessionTable
    with TableInfo<$SessionTableTable, SessionRow> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $SessionTableTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _idMeta = const VerificationMeta('id');
  @override
  late final GeneratedColumn<int> id = GeneratedColumn<int>(
    'id',
    aliasedName,
    false,
    type: DriftSqlType.int,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _userIdMeta = const VerificationMeta('userId');
  @override
  late final GeneratedColumn<String> userId = GeneratedColumn<String>(
    'user_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _emailMeta = const VerificationMeta('email');
  @override
  late final GeneratedColumn<String> email = GeneratedColumn<String>(
    'email',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _fullNameMeta = const VerificationMeta(
    'fullName',
  );
  @override
  late final GeneratedColumn<String> fullName = GeneratedColumn<String>(
    'full_name',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _membershipsJsonMeta = const VerificationMeta(
    'membershipsJson',
  );
  @override
  late final GeneratedColumn<String> membershipsJson = GeneratedColumn<String>(
    'memberships_json',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _selectedOrgIdMeta = const VerificationMeta(
    'selectedOrgId',
  );
  @override
  late final GeneratedColumn<String> selectedOrgId = GeneratedColumn<String>(
    'selected_org_id',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _expiresAtMeta = const VerificationMeta(
    'expiresAt',
  );
  @override
  late final GeneratedColumn<DateTime> expiresAt = GeneratedColumn<DateTime>(
    'expires_at',
    aliasedName,
    true,
    type: DriftSqlType.dateTime,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _updatedAtMeta = const VerificationMeta(
    'updatedAt',
  );
  @override
  late final GeneratedColumn<DateTime> updatedAt = GeneratedColumn<DateTime>(
    'updated_at',
    aliasedName,
    false,
    type: DriftSqlType.dateTime,
    requiredDuringInsert: true,
  );
  @override
  List<GeneratedColumn> get $columns => [
    id,
    userId,
    email,
    fullName,
    membershipsJson,
    selectedOrgId,
    expiresAt,
    updatedAt,
  ];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'session';
  @override
  VerificationContext validateIntegrity(
    Insertable<SessionRow> instance, {
    bool isInserting = false,
  }) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('id')) {
      context.handle(_idMeta, id.isAcceptableOrUnknown(data['id']!, _idMeta));
    }
    if (data.containsKey('user_id')) {
      context.handle(
        _userIdMeta,
        userId.isAcceptableOrUnknown(data['user_id']!, _userIdMeta),
      );
    } else if (isInserting) {
      context.missing(_userIdMeta);
    }
    if (data.containsKey('email')) {
      context.handle(
        _emailMeta,
        email.isAcceptableOrUnknown(data['email']!, _emailMeta),
      );
    } else if (isInserting) {
      context.missing(_emailMeta);
    }
    if (data.containsKey('full_name')) {
      context.handle(
        _fullNameMeta,
        fullName.isAcceptableOrUnknown(data['full_name']!, _fullNameMeta),
      );
    } else if (isInserting) {
      context.missing(_fullNameMeta);
    }
    if (data.containsKey('memberships_json')) {
      context.handle(
        _membershipsJsonMeta,
        membershipsJson.isAcceptableOrUnknown(
          data['memberships_json']!,
          _membershipsJsonMeta,
        ),
      );
    } else if (isInserting) {
      context.missing(_membershipsJsonMeta);
    }
    if (data.containsKey('selected_org_id')) {
      context.handle(
        _selectedOrgIdMeta,
        selectedOrgId.isAcceptableOrUnknown(
          data['selected_org_id']!,
          _selectedOrgIdMeta,
        ),
      );
    }
    if (data.containsKey('expires_at')) {
      context.handle(
        _expiresAtMeta,
        expiresAt.isAcceptableOrUnknown(data['expires_at']!, _expiresAtMeta),
      );
    }
    if (data.containsKey('updated_at')) {
      context.handle(
        _updatedAtMeta,
        updatedAt.isAcceptableOrUnknown(data['updated_at']!, _updatedAtMeta),
      );
    } else if (isInserting) {
      context.missing(_updatedAtMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {id};
  @override
  SessionRow map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return SessionRow(
      id: attachedDatabase.typeMapping.read(
        DriftSqlType.int,
        data['${effectivePrefix}id'],
      )!,
      userId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}user_id'],
      )!,
      email: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}email'],
      )!,
      fullName: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}full_name'],
      )!,
      membershipsJson: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}memberships_json'],
      )!,
      selectedOrgId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}selected_org_id'],
      ),
      expiresAt: attachedDatabase.typeMapping.read(
        DriftSqlType.dateTime,
        data['${effectivePrefix}expires_at'],
      ),
      updatedAt: attachedDatabase.typeMapping.read(
        DriftSqlType.dateTime,
        data['${effectivePrefix}updated_at'],
      )!,
    );
  }

  @override
  $SessionTableTable createAlias(String alias) {
    return $SessionTableTable(attachedDatabase, alias);
  }
}

class SessionRow extends DataClass implements Insertable<SessionRow> {
  final int id;
  final String userId;
  final String email;
  final String fullName;
  final String membershipsJson;
  final String? selectedOrgId;
  final DateTime? expiresAt;
  final DateTime updatedAt;
  const SessionRow({
    required this.id,
    required this.userId,
    required this.email,
    required this.fullName,
    required this.membershipsJson,
    this.selectedOrgId,
    this.expiresAt,
    required this.updatedAt,
  });
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['id'] = Variable<int>(id);
    map['user_id'] = Variable<String>(userId);
    map['email'] = Variable<String>(email);
    map['full_name'] = Variable<String>(fullName);
    map['memberships_json'] = Variable<String>(membershipsJson);
    if (!nullToAbsent || selectedOrgId != null) {
      map['selected_org_id'] = Variable<String>(selectedOrgId);
    }
    if (!nullToAbsent || expiresAt != null) {
      map['expires_at'] = Variable<DateTime>(expiresAt);
    }
    map['updated_at'] = Variable<DateTime>(updatedAt);
    return map;
  }

  SessionTableCompanion toCompanion(bool nullToAbsent) {
    return SessionTableCompanion(
      id: Value(id),
      userId: Value(userId),
      email: Value(email),
      fullName: Value(fullName),
      membershipsJson: Value(membershipsJson),
      selectedOrgId: selectedOrgId == null && nullToAbsent
          ? const Value.absent()
          : Value(selectedOrgId),
      expiresAt: expiresAt == null && nullToAbsent
          ? const Value.absent()
          : Value(expiresAt),
      updatedAt: Value(updatedAt),
    );
  }

  factory SessionRow.fromJson(
    Map<String, dynamic> json, {
    ValueSerializer? serializer,
  }) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return SessionRow(
      id: serializer.fromJson<int>(json['id']),
      userId: serializer.fromJson<String>(json['userId']),
      email: serializer.fromJson<String>(json['email']),
      fullName: serializer.fromJson<String>(json['fullName']),
      membershipsJson: serializer.fromJson<String>(json['membershipsJson']),
      selectedOrgId: serializer.fromJson<String?>(json['selectedOrgId']),
      expiresAt: serializer.fromJson<DateTime?>(json['expiresAt']),
      updatedAt: serializer.fromJson<DateTime>(json['updatedAt']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'id': serializer.toJson<int>(id),
      'userId': serializer.toJson<String>(userId),
      'email': serializer.toJson<String>(email),
      'fullName': serializer.toJson<String>(fullName),
      'membershipsJson': serializer.toJson<String>(membershipsJson),
      'selectedOrgId': serializer.toJson<String?>(selectedOrgId),
      'expiresAt': serializer.toJson<DateTime?>(expiresAt),
      'updatedAt': serializer.toJson<DateTime>(updatedAt),
    };
  }

  SessionRow copyWith({
    int? id,
    String? userId,
    String? email,
    String? fullName,
    String? membershipsJson,
    Value<String?> selectedOrgId = const Value.absent(),
    Value<DateTime?> expiresAt = const Value.absent(),
    DateTime? updatedAt,
  }) => SessionRow(
    id: id ?? this.id,
    userId: userId ?? this.userId,
    email: email ?? this.email,
    fullName: fullName ?? this.fullName,
    membershipsJson: membershipsJson ?? this.membershipsJson,
    selectedOrgId: selectedOrgId.present
        ? selectedOrgId.value
        : this.selectedOrgId,
    expiresAt: expiresAt.present ? expiresAt.value : this.expiresAt,
    updatedAt: updatedAt ?? this.updatedAt,
  );
  SessionRow copyWithCompanion(SessionTableCompanion data) {
    return SessionRow(
      id: data.id.present ? data.id.value : this.id,
      userId: data.userId.present ? data.userId.value : this.userId,
      email: data.email.present ? data.email.value : this.email,
      fullName: data.fullName.present ? data.fullName.value : this.fullName,
      membershipsJson: data.membershipsJson.present
          ? data.membershipsJson.value
          : this.membershipsJson,
      selectedOrgId: data.selectedOrgId.present
          ? data.selectedOrgId.value
          : this.selectedOrgId,
      expiresAt: data.expiresAt.present ? data.expiresAt.value : this.expiresAt,
      updatedAt: data.updatedAt.present ? data.updatedAt.value : this.updatedAt,
    );
  }

  @override
  String toString() {
    return (StringBuffer('SessionRow(')
          ..write('id: $id, ')
          ..write('userId: $userId, ')
          ..write('email: $email, ')
          ..write('fullName: $fullName, ')
          ..write('membershipsJson: $membershipsJson, ')
          ..write('selectedOrgId: $selectedOrgId, ')
          ..write('expiresAt: $expiresAt, ')
          ..write('updatedAt: $updatedAt')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(
    id,
    userId,
    email,
    fullName,
    membershipsJson,
    selectedOrgId,
    expiresAt,
    updatedAt,
  );
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is SessionRow &&
          other.id == this.id &&
          other.userId == this.userId &&
          other.email == this.email &&
          other.fullName == this.fullName &&
          other.membershipsJson == this.membershipsJson &&
          other.selectedOrgId == this.selectedOrgId &&
          other.expiresAt == this.expiresAt &&
          other.updatedAt == this.updatedAt);
}

class SessionTableCompanion extends UpdateCompanion<SessionRow> {
  final Value<int> id;
  final Value<String> userId;
  final Value<String> email;
  final Value<String> fullName;
  final Value<String> membershipsJson;
  final Value<String?> selectedOrgId;
  final Value<DateTime?> expiresAt;
  final Value<DateTime> updatedAt;
  const SessionTableCompanion({
    this.id = const Value.absent(),
    this.userId = const Value.absent(),
    this.email = const Value.absent(),
    this.fullName = const Value.absent(),
    this.membershipsJson = const Value.absent(),
    this.selectedOrgId = const Value.absent(),
    this.expiresAt = const Value.absent(),
    this.updatedAt = const Value.absent(),
  });
  SessionTableCompanion.insert({
    this.id = const Value.absent(),
    required String userId,
    required String email,
    required String fullName,
    required String membershipsJson,
    this.selectedOrgId = const Value.absent(),
    this.expiresAt = const Value.absent(),
    required DateTime updatedAt,
  }) : userId = Value(userId),
       email = Value(email),
       fullName = Value(fullName),
       membershipsJson = Value(membershipsJson),
       updatedAt = Value(updatedAt);
  static Insertable<SessionRow> custom({
    Expression<int>? id,
    Expression<String>? userId,
    Expression<String>? email,
    Expression<String>? fullName,
    Expression<String>? membershipsJson,
    Expression<String>? selectedOrgId,
    Expression<DateTime>? expiresAt,
    Expression<DateTime>? updatedAt,
  }) {
    return RawValuesInsertable({
      if (id != null) 'id': id,
      if (userId != null) 'user_id': userId,
      if (email != null) 'email': email,
      if (fullName != null) 'full_name': fullName,
      if (membershipsJson != null) 'memberships_json': membershipsJson,
      if (selectedOrgId != null) 'selected_org_id': selectedOrgId,
      if (expiresAt != null) 'expires_at': expiresAt,
      if (updatedAt != null) 'updated_at': updatedAt,
    });
  }

  SessionTableCompanion copyWith({
    Value<int>? id,
    Value<String>? userId,
    Value<String>? email,
    Value<String>? fullName,
    Value<String>? membershipsJson,
    Value<String?>? selectedOrgId,
    Value<DateTime?>? expiresAt,
    Value<DateTime>? updatedAt,
  }) {
    return SessionTableCompanion(
      id: id ?? this.id,
      userId: userId ?? this.userId,
      email: email ?? this.email,
      fullName: fullName ?? this.fullName,
      membershipsJson: membershipsJson ?? this.membershipsJson,
      selectedOrgId: selectedOrgId ?? this.selectedOrgId,
      expiresAt: expiresAt ?? this.expiresAt,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (id.present) {
      map['id'] = Variable<int>(id.value);
    }
    if (userId.present) {
      map['user_id'] = Variable<String>(userId.value);
    }
    if (email.present) {
      map['email'] = Variable<String>(email.value);
    }
    if (fullName.present) {
      map['full_name'] = Variable<String>(fullName.value);
    }
    if (membershipsJson.present) {
      map['memberships_json'] = Variable<String>(membershipsJson.value);
    }
    if (selectedOrgId.present) {
      map['selected_org_id'] = Variable<String>(selectedOrgId.value);
    }
    if (expiresAt.present) {
      map['expires_at'] = Variable<DateTime>(expiresAt.value);
    }
    if (updatedAt.present) {
      map['updated_at'] = Variable<DateTime>(updatedAt.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('SessionTableCompanion(')
          ..write('id: $id, ')
          ..write('userId: $userId, ')
          ..write('email: $email, ')
          ..write('fullName: $fullName, ')
          ..write('membershipsJson: $membershipsJson, ')
          ..write('selectedOrgId: $selectedOrgId, ')
          ..write('expiresAt: $expiresAt, ')
          ..write('updatedAt: $updatedAt')
          ..write(')'))
        .toString();
  }
}

class $CachedJobsTable extends CachedJobs
    with TableInfo<$CachedJobsTable, CachedJobRow> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $CachedJobsTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _orgIdMeta = const VerificationMeta('orgId');
  @override
  late final GeneratedColumn<String> orgId = GeneratedColumn<String>(
    'org_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _requestIdMeta = const VerificationMeta(
    'requestId',
  );
  @override
  late final GeneratedColumn<String> requestId = GeneratedColumn<String>(
    'request_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _assignmentIdMeta = const VerificationMeta(
    'assignmentId',
  );
  @override
  late final GeneratedColumn<String> assignmentId = GeneratedColumn<String>(
    'assignment_id',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _scopeMeta = const VerificationMeta('scope');
  @override
  late final GeneratedColumn<String> scope = GeneratedColumn<String>(
    'scope',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _itemJsonMeta = const VerificationMeta(
    'itemJson',
  );
  @override
  late final GeneratedColumn<String> itemJson = GeneratedColumn<String>(
    'item_json',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _detailJsonMeta = const VerificationMeta(
    'detailJson',
  );
  @override
  late final GeneratedColumn<String> detailJson = GeneratedColumn<String>(
    'detail_json',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _fetchedAtMeta = const VerificationMeta(
    'fetchedAt',
  );
  @override
  late final GeneratedColumn<DateTime> fetchedAt = GeneratedColumn<DateTime>(
    'fetched_at',
    aliasedName,
    false,
    type: DriftSqlType.dateTime,
    requiredDuringInsert: true,
  );
  @override
  List<GeneratedColumn> get $columns => [
    orgId,
    requestId,
    assignmentId,
    scope,
    itemJson,
    detailJson,
    fetchedAt,
  ];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'cached_jobs';
  @override
  VerificationContext validateIntegrity(
    Insertable<CachedJobRow> instance, {
    bool isInserting = false,
  }) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('org_id')) {
      context.handle(
        _orgIdMeta,
        orgId.isAcceptableOrUnknown(data['org_id']!, _orgIdMeta),
      );
    } else if (isInserting) {
      context.missing(_orgIdMeta);
    }
    if (data.containsKey('request_id')) {
      context.handle(
        _requestIdMeta,
        requestId.isAcceptableOrUnknown(data['request_id']!, _requestIdMeta),
      );
    } else if (isInserting) {
      context.missing(_requestIdMeta);
    }
    if (data.containsKey('assignment_id')) {
      context.handle(
        _assignmentIdMeta,
        assignmentId.isAcceptableOrUnknown(
          data['assignment_id']!,
          _assignmentIdMeta,
        ),
      );
    }
    if (data.containsKey('scope')) {
      context.handle(
        _scopeMeta,
        scope.isAcceptableOrUnknown(data['scope']!, _scopeMeta),
      );
    }
    if (data.containsKey('item_json')) {
      context.handle(
        _itemJsonMeta,
        itemJson.isAcceptableOrUnknown(data['item_json']!, _itemJsonMeta),
      );
    }
    if (data.containsKey('detail_json')) {
      context.handle(
        _detailJsonMeta,
        detailJson.isAcceptableOrUnknown(data['detail_json']!, _detailJsonMeta),
      );
    }
    if (data.containsKey('fetched_at')) {
      context.handle(
        _fetchedAtMeta,
        fetchedAt.isAcceptableOrUnknown(data['fetched_at']!, _fetchedAtMeta),
      );
    } else if (isInserting) {
      context.missing(_fetchedAtMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {orgId, requestId};
  @override
  CachedJobRow map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return CachedJobRow(
      orgId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}org_id'],
      )!,
      requestId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}request_id'],
      )!,
      assignmentId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}assignment_id'],
      ),
      scope: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}scope'],
      ),
      itemJson: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}item_json'],
      ),
      detailJson: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}detail_json'],
      ),
      fetchedAt: attachedDatabase.typeMapping.read(
        DriftSqlType.dateTime,
        data['${effectivePrefix}fetched_at'],
      )!,
    );
  }

  @override
  $CachedJobsTable createAlias(String alias) {
    return $CachedJobsTable(attachedDatabase, alias);
  }
}

class CachedJobRow extends DataClass implements Insertable<CachedJobRow> {
  final String orgId;
  final String requestId;
  final String? assignmentId;
  final String? scope;
  final String? itemJson;
  final String? detailJson;
  final DateTime fetchedAt;
  const CachedJobRow({
    required this.orgId,
    required this.requestId,
    this.assignmentId,
    this.scope,
    this.itemJson,
    this.detailJson,
    required this.fetchedAt,
  });
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['org_id'] = Variable<String>(orgId);
    map['request_id'] = Variable<String>(requestId);
    if (!nullToAbsent || assignmentId != null) {
      map['assignment_id'] = Variable<String>(assignmentId);
    }
    if (!nullToAbsent || scope != null) {
      map['scope'] = Variable<String>(scope);
    }
    if (!nullToAbsent || itemJson != null) {
      map['item_json'] = Variable<String>(itemJson);
    }
    if (!nullToAbsent || detailJson != null) {
      map['detail_json'] = Variable<String>(detailJson);
    }
    map['fetched_at'] = Variable<DateTime>(fetchedAt);
    return map;
  }

  CachedJobsCompanion toCompanion(bool nullToAbsent) {
    return CachedJobsCompanion(
      orgId: Value(orgId),
      requestId: Value(requestId),
      assignmentId: assignmentId == null && nullToAbsent
          ? const Value.absent()
          : Value(assignmentId),
      scope: scope == null && nullToAbsent
          ? const Value.absent()
          : Value(scope),
      itemJson: itemJson == null && nullToAbsent
          ? const Value.absent()
          : Value(itemJson),
      detailJson: detailJson == null && nullToAbsent
          ? const Value.absent()
          : Value(detailJson),
      fetchedAt: Value(fetchedAt),
    );
  }

  factory CachedJobRow.fromJson(
    Map<String, dynamic> json, {
    ValueSerializer? serializer,
  }) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return CachedJobRow(
      orgId: serializer.fromJson<String>(json['orgId']),
      requestId: serializer.fromJson<String>(json['requestId']),
      assignmentId: serializer.fromJson<String?>(json['assignmentId']),
      scope: serializer.fromJson<String?>(json['scope']),
      itemJson: serializer.fromJson<String?>(json['itemJson']),
      detailJson: serializer.fromJson<String?>(json['detailJson']),
      fetchedAt: serializer.fromJson<DateTime>(json['fetchedAt']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'orgId': serializer.toJson<String>(orgId),
      'requestId': serializer.toJson<String>(requestId),
      'assignmentId': serializer.toJson<String?>(assignmentId),
      'scope': serializer.toJson<String?>(scope),
      'itemJson': serializer.toJson<String?>(itemJson),
      'detailJson': serializer.toJson<String?>(detailJson),
      'fetchedAt': serializer.toJson<DateTime>(fetchedAt),
    };
  }

  CachedJobRow copyWith({
    String? orgId,
    String? requestId,
    Value<String?> assignmentId = const Value.absent(),
    Value<String?> scope = const Value.absent(),
    Value<String?> itemJson = const Value.absent(),
    Value<String?> detailJson = const Value.absent(),
    DateTime? fetchedAt,
  }) => CachedJobRow(
    orgId: orgId ?? this.orgId,
    requestId: requestId ?? this.requestId,
    assignmentId: assignmentId.present ? assignmentId.value : this.assignmentId,
    scope: scope.present ? scope.value : this.scope,
    itemJson: itemJson.present ? itemJson.value : this.itemJson,
    detailJson: detailJson.present ? detailJson.value : this.detailJson,
    fetchedAt: fetchedAt ?? this.fetchedAt,
  );
  CachedJobRow copyWithCompanion(CachedJobsCompanion data) {
    return CachedJobRow(
      orgId: data.orgId.present ? data.orgId.value : this.orgId,
      requestId: data.requestId.present ? data.requestId.value : this.requestId,
      assignmentId: data.assignmentId.present
          ? data.assignmentId.value
          : this.assignmentId,
      scope: data.scope.present ? data.scope.value : this.scope,
      itemJson: data.itemJson.present ? data.itemJson.value : this.itemJson,
      detailJson: data.detailJson.present
          ? data.detailJson.value
          : this.detailJson,
      fetchedAt: data.fetchedAt.present ? data.fetchedAt.value : this.fetchedAt,
    );
  }

  @override
  String toString() {
    return (StringBuffer('CachedJobRow(')
          ..write('orgId: $orgId, ')
          ..write('requestId: $requestId, ')
          ..write('assignmentId: $assignmentId, ')
          ..write('scope: $scope, ')
          ..write('itemJson: $itemJson, ')
          ..write('detailJson: $detailJson, ')
          ..write('fetchedAt: $fetchedAt')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(
    orgId,
    requestId,
    assignmentId,
    scope,
    itemJson,
    detailJson,
    fetchedAt,
  );
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is CachedJobRow &&
          other.orgId == this.orgId &&
          other.requestId == this.requestId &&
          other.assignmentId == this.assignmentId &&
          other.scope == this.scope &&
          other.itemJson == this.itemJson &&
          other.detailJson == this.detailJson &&
          other.fetchedAt == this.fetchedAt);
}

class CachedJobsCompanion extends UpdateCompanion<CachedJobRow> {
  final Value<String> orgId;
  final Value<String> requestId;
  final Value<String?> assignmentId;
  final Value<String?> scope;
  final Value<String?> itemJson;
  final Value<String?> detailJson;
  final Value<DateTime> fetchedAt;
  final Value<int> rowid;
  const CachedJobsCompanion({
    this.orgId = const Value.absent(),
    this.requestId = const Value.absent(),
    this.assignmentId = const Value.absent(),
    this.scope = const Value.absent(),
    this.itemJson = const Value.absent(),
    this.detailJson = const Value.absent(),
    this.fetchedAt = const Value.absent(),
    this.rowid = const Value.absent(),
  });
  CachedJobsCompanion.insert({
    required String orgId,
    required String requestId,
    this.assignmentId = const Value.absent(),
    this.scope = const Value.absent(),
    this.itemJson = const Value.absent(),
    this.detailJson = const Value.absent(),
    required DateTime fetchedAt,
    this.rowid = const Value.absent(),
  }) : orgId = Value(orgId),
       requestId = Value(requestId),
       fetchedAt = Value(fetchedAt);
  static Insertable<CachedJobRow> custom({
    Expression<String>? orgId,
    Expression<String>? requestId,
    Expression<String>? assignmentId,
    Expression<String>? scope,
    Expression<String>? itemJson,
    Expression<String>? detailJson,
    Expression<DateTime>? fetchedAt,
    Expression<int>? rowid,
  }) {
    return RawValuesInsertable({
      if (orgId != null) 'org_id': orgId,
      if (requestId != null) 'request_id': requestId,
      if (assignmentId != null) 'assignment_id': assignmentId,
      if (scope != null) 'scope': scope,
      if (itemJson != null) 'item_json': itemJson,
      if (detailJson != null) 'detail_json': detailJson,
      if (fetchedAt != null) 'fetched_at': fetchedAt,
      if (rowid != null) 'rowid': rowid,
    });
  }

  CachedJobsCompanion copyWith({
    Value<String>? orgId,
    Value<String>? requestId,
    Value<String?>? assignmentId,
    Value<String?>? scope,
    Value<String?>? itemJson,
    Value<String?>? detailJson,
    Value<DateTime>? fetchedAt,
    Value<int>? rowid,
  }) {
    return CachedJobsCompanion(
      orgId: orgId ?? this.orgId,
      requestId: requestId ?? this.requestId,
      assignmentId: assignmentId ?? this.assignmentId,
      scope: scope ?? this.scope,
      itemJson: itemJson ?? this.itemJson,
      detailJson: detailJson ?? this.detailJson,
      fetchedAt: fetchedAt ?? this.fetchedAt,
      rowid: rowid ?? this.rowid,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (orgId.present) {
      map['org_id'] = Variable<String>(orgId.value);
    }
    if (requestId.present) {
      map['request_id'] = Variable<String>(requestId.value);
    }
    if (assignmentId.present) {
      map['assignment_id'] = Variable<String>(assignmentId.value);
    }
    if (scope.present) {
      map['scope'] = Variable<String>(scope.value);
    }
    if (itemJson.present) {
      map['item_json'] = Variable<String>(itemJson.value);
    }
    if (detailJson.present) {
      map['detail_json'] = Variable<String>(detailJson.value);
    }
    if (fetchedAt.present) {
      map['fetched_at'] = Variable<DateTime>(fetchedAt.value);
    }
    if (rowid.present) {
      map['rowid'] = Variable<int>(rowid.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('CachedJobsCompanion(')
          ..write('orgId: $orgId, ')
          ..write('requestId: $requestId, ')
          ..write('assignmentId: $assignmentId, ')
          ..write('scope: $scope, ')
          ..write('itemJson: $itemJson, ')
          ..write('detailJson: $detailJson, ')
          ..write('fetchedAt: $fetchedAt, ')
          ..write('rowid: $rowid')
          ..write(')'))
        .toString();
  }
}

class $PendingCommandsTable extends PendingCommands
    with TableInfo<$PendingCommandsTable, PendingCommandRow> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $PendingCommandsTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _idMeta = const VerificationMeta('id');
  @override
  late final GeneratedColumn<int> id = GeneratedColumn<int>(
    'id',
    aliasedName,
    false,
    hasAutoIncrement: true,
    type: DriftSqlType.int,
    requiredDuringInsert: false,
    defaultConstraints: GeneratedColumn.constraintIsAlways(
      'PRIMARY KEY AUTOINCREMENT',
    ),
  );
  static const VerificationMeta _clientCommandIdMeta = const VerificationMeta(
    'clientCommandId',
  );
  @override
  late final GeneratedColumn<String> clientCommandId = GeneratedColumn<String>(
    'client_command_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
    defaultConstraints: GeneratedColumn.constraintIsAlways('UNIQUE'),
  );
  static const VerificationMeta _orgIdMeta = const VerificationMeta('orgId');
  @override
  late final GeneratedColumn<String> orgId = GeneratedColumn<String>(
    'org_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _requestIdMeta = const VerificationMeta(
    'requestId',
  );
  @override
  late final GeneratedColumn<String> requestId = GeneratedColumn<String>(
    'request_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _typeMeta = const VerificationMeta('type');
  @override
  late final GeneratedColumn<String> type = GeneratedColumn<String>(
    'type',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _payloadJsonMeta = const VerificationMeta(
    'payloadJson',
  );
  @override
  late final GeneratedColumn<String> payloadJson = GeneratedColumn<String>(
    'payload_json',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _statusMeta = const VerificationMeta('status');
  @override
  late final GeneratedColumn<String> status = GeneratedColumn<String>(
    'status',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
    defaultValue: const Constant('PENDING'),
  );
  static const VerificationMeta _attemptsMeta = const VerificationMeta(
    'attempts',
  );
  @override
  late final GeneratedColumn<int> attempts = GeneratedColumn<int>(
    'attempts',
    aliasedName,
    false,
    type: DriftSqlType.int,
    requiredDuringInsert: false,
    defaultValue: const Constant(0),
  );
  static const VerificationMeta _lastErrorMeta = const VerificationMeta(
    'lastError',
  );
  @override
  late final GeneratedColumn<String> lastError = GeneratedColumn<String>(
    'last_error',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _nextAttemptAtMeta = const VerificationMeta(
    'nextAttemptAt',
  );
  @override
  late final GeneratedColumn<DateTime> nextAttemptAt =
      GeneratedColumn<DateTime>(
        'next_attempt_at',
        aliasedName,
        true,
        type: DriftSqlType.dateTime,
        requiredDuringInsert: false,
      );
  static const VerificationMeta _createdAtMeta = const VerificationMeta(
    'createdAt',
  );
  @override
  late final GeneratedColumn<DateTime> createdAt = GeneratedColumn<DateTime>(
    'created_at',
    aliasedName,
    false,
    type: DriftSqlType.dateTime,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _updatedAtMeta = const VerificationMeta(
    'updatedAt',
  );
  @override
  late final GeneratedColumn<DateTime> updatedAt = GeneratedColumn<DateTime>(
    'updated_at',
    aliasedName,
    false,
    type: DriftSqlType.dateTime,
    requiredDuringInsert: true,
  );
  @override
  List<GeneratedColumn> get $columns => [
    id,
    clientCommandId,
    orgId,
    requestId,
    type,
    payloadJson,
    status,
    attempts,
    lastError,
    nextAttemptAt,
    createdAt,
    updatedAt,
  ];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'pending_commands';
  @override
  VerificationContext validateIntegrity(
    Insertable<PendingCommandRow> instance, {
    bool isInserting = false,
  }) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('id')) {
      context.handle(_idMeta, id.isAcceptableOrUnknown(data['id']!, _idMeta));
    }
    if (data.containsKey('client_command_id')) {
      context.handle(
        _clientCommandIdMeta,
        clientCommandId.isAcceptableOrUnknown(
          data['client_command_id']!,
          _clientCommandIdMeta,
        ),
      );
    } else if (isInserting) {
      context.missing(_clientCommandIdMeta);
    }
    if (data.containsKey('org_id')) {
      context.handle(
        _orgIdMeta,
        orgId.isAcceptableOrUnknown(data['org_id']!, _orgIdMeta),
      );
    } else if (isInserting) {
      context.missing(_orgIdMeta);
    }
    if (data.containsKey('request_id')) {
      context.handle(
        _requestIdMeta,
        requestId.isAcceptableOrUnknown(data['request_id']!, _requestIdMeta),
      );
    } else if (isInserting) {
      context.missing(_requestIdMeta);
    }
    if (data.containsKey('type')) {
      context.handle(
        _typeMeta,
        type.isAcceptableOrUnknown(data['type']!, _typeMeta),
      );
    } else if (isInserting) {
      context.missing(_typeMeta);
    }
    if (data.containsKey('payload_json')) {
      context.handle(
        _payloadJsonMeta,
        payloadJson.isAcceptableOrUnknown(
          data['payload_json']!,
          _payloadJsonMeta,
        ),
      );
    } else if (isInserting) {
      context.missing(_payloadJsonMeta);
    }
    if (data.containsKey('status')) {
      context.handle(
        _statusMeta,
        status.isAcceptableOrUnknown(data['status']!, _statusMeta),
      );
    }
    if (data.containsKey('attempts')) {
      context.handle(
        _attemptsMeta,
        attempts.isAcceptableOrUnknown(data['attempts']!, _attemptsMeta),
      );
    }
    if (data.containsKey('last_error')) {
      context.handle(
        _lastErrorMeta,
        lastError.isAcceptableOrUnknown(data['last_error']!, _lastErrorMeta),
      );
    }
    if (data.containsKey('next_attempt_at')) {
      context.handle(
        _nextAttemptAtMeta,
        nextAttemptAt.isAcceptableOrUnknown(
          data['next_attempt_at']!,
          _nextAttemptAtMeta,
        ),
      );
    }
    if (data.containsKey('created_at')) {
      context.handle(
        _createdAtMeta,
        createdAt.isAcceptableOrUnknown(data['created_at']!, _createdAtMeta),
      );
    } else if (isInserting) {
      context.missing(_createdAtMeta);
    }
    if (data.containsKey('updated_at')) {
      context.handle(
        _updatedAtMeta,
        updatedAt.isAcceptableOrUnknown(data['updated_at']!, _updatedAtMeta),
      );
    } else if (isInserting) {
      context.missing(_updatedAtMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {id};
  @override
  PendingCommandRow map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return PendingCommandRow(
      id: attachedDatabase.typeMapping.read(
        DriftSqlType.int,
        data['${effectivePrefix}id'],
      )!,
      clientCommandId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}client_command_id'],
      )!,
      orgId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}org_id'],
      )!,
      requestId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}request_id'],
      )!,
      type: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}type'],
      )!,
      payloadJson: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}payload_json'],
      )!,
      status: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}status'],
      )!,
      attempts: attachedDatabase.typeMapping.read(
        DriftSqlType.int,
        data['${effectivePrefix}attempts'],
      )!,
      lastError: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}last_error'],
      ),
      nextAttemptAt: attachedDatabase.typeMapping.read(
        DriftSqlType.dateTime,
        data['${effectivePrefix}next_attempt_at'],
      ),
      createdAt: attachedDatabase.typeMapping.read(
        DriftSqlType.dateTime,
        data['${effectivePrefix}created_at'],
      )!,
      updatedAt: attachedDatabase.typeMapping.read(
        DriftSqlType.dateTime,
        data['${effectivePrefix}updated_at'],
      )!,
    );
  }

  @override
  $PendingCommandsTable createAlias(String alias) {
    return $PendingCommandsTable(attachedDatabase, alias);
  }
}

class PendingCommandRow extends DataClass
    implements Insertable<PendingCommandRow> {
  final int id;
  final String clientCommandId;
  final String orgId;
  final String requestId;
  final String type;
  final String payloadJson;
  final String status;
  final int attempts;
  final String? lastError;
  final DateTime? nextAttemptAt;
  final DateTime createdAt;
  final DateTime updatedAt;
  const PendingCommandRow({
    required this.id,
    required this.clientCommandId,
    required this.orgId,
    required this.requestId,
    required this.type,
    required this.payloadJson,
    required this.status,
    required this.attempts,
    this.lastError,
    this.nextAttemptAt,
    required this.createdAt,
    required this.updatedAt,
  });
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['id'] = Variable<int>(id);
    map['client_command_id'] = Variable<String>(clientCommandId);
    map['org_id'] = Variable<String>(orgId);
    map['request_id'] = Variable<String>(requestId);
    map['type'] = Variable<String>(type);
    map['payload_json'] = Variable<String>(payloadJson);
    map['status'] = Variable<String>(status);
    map['attempts'] = Variable<int>(attempts);
    if (!nullToAbsent || lastError != null) {
      map['last_error'] = Variable<String>(lastError);
    }
    if (!nullToAbsent || nextAttemptAt != null) {
      map['next_attempt_at'] = Variable<DateTime>(nextAttemptAt);
    }
    map['created_at'] = Variable<DateTime>(createdAt);
    map['updated_at'] = Variable<DateTime>(updatedAt);
    return map;
  }

  PendingCommandsCompanion toCompanion(bool nullToAbsent) {
    return PendingCommandsCompanion(
      id: Value(id),
      clientCommandId: Value(clientCommandId),
      orgId: Value(orgId),
      requestId: Value(requestId),
      type: Value(type),
      payloadJson: Value(payloadJson),
      status: Value(status),
      attempts: Value(attempts),
      lastError: lastError == null && nullToAbsent
          ? const Value.absent()
          : Value(lastError),
      nextAttemptAt: nextAttemptAt == null && nullToAbsent
          ? const Value.absent()
          : Value(nextAttemptAt),
      createdAt: Value(createdAt),
      updatedAt: Value(updatedAt),
    );
  }

  factory PendingCommandRow.fromJson(
    Map<String, dynamic> json, {
    ValueSerializer? serializer,
  }) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return PendingCommandRow(
      id: serializer.fromJson<int>(json['id']),
      clientCommandId: serializer.fromJson<String>(json['clientCommandId']),
      orgId: serializer.fromJson<String>(json['orgId']),
      requestId: serializer.fromJson<String>(json['requestId']),
      type: serializer.fromJson<String>(json['type']),
      payloadJson: serializer.fromJson<String>(json['payloadJson']),
      status: serializer.fromJson<String>(json['status']),
      attempts: serializer.fromJson<int>(json['attempts']),
      lastError: serializer.fromJson<String?>(json['lastError']),
      nextAttemptAt: serializer.fromJson<DateTime?>(json['nextAttemptAt']),
      createdAt: serializer.fromJson<DateTime>(json['createdAt']),
      updatedAt: serializer.fromJson<DateTime>(json['updatedAt']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'id': serializer.toJson<int>(id),
      'clientCommandId': serializer.toJson<String>(clientCommandId),
      'orgId': serializer.toJson<String>(orgId),
      'requestId': serializer.toJson<String>(requestId),
      'type': serializer.toJson<String>(type),
      'payloadJson': serializer.toJson<String>(payloadJson),
      'status': serializer.toJson<String>(status),
      'attempts': serializer.toJson<int>(attempts),
      'lastError': serializer.toJson<String?>(lastError),
      'nextAttemptAt': serializer.toJson<DateTime?>(nextAttemptAt),
      'createdAt': serializer.toJson<DateTime>(createdAt),
      'updatedAt': serializer.toJson<DateTime>(updatedAt),
    };
  }

  PendingCommandRow copyWith({
    int? id,
    String? clientCommandId,
    String? orgId,
    String? requestId,
    String? type,
    String? payloadJson,
    String? status,
    int? attempts,
    Value<String?> lastError = const Value.absent(),
    Value<DateTime?> nextAttemptAt = const Value.absent(),
    DateTime? createdAt,
    DateTime? updatedAt,
  }) => PendingCommandRow(
    id: id ?? this.id,
    clientCommandId: clientCommandId ?? this.clientCommandId,
    orgId: orgId ?? this.orgId,
    requestId: requestId ?? this.requestId,
    type: type ?? this.type,
    payloadJson: payloadJson ?? this.payloadJson,
    status: status ?? this.status,
    attempts: attempts ?? this.attempts,
    lastError: lastError.present ? lastError.value : this.lastError,
    nextAttemptAt: nextAttemptAt.present
        ? nextAttemptAt.value
        : this.nextAttemptAt,
    createdAt: createdAt ?? this.createdAt,
    updatedAt: updatedAt ?? this.updatedAt,
  );
  PendingCommandRow copyWithCompanion(PendingCommandsCompanion data) {
    return PendingCommandRow(
      id: data.id.present ? data.id.value : this.id,
      clientCommandId: data.clientCommandId.present
          ? data.clientCommandId.value
          : this.clientCommandId,
      orgId: data.orgId.present ? data.orgId.value : this.orgId,
      requestId: data.requestId.present ? data.requestId.value : this.requestId,
      type: data.type.present ? data.type.value : this.type,
      payloadJson: data.payloadJson.present
          ? data.payloadJson.value
          : this.payloadJson,
      status: data.status.present ? data.status.value : this.status,
      attempts: data.attempts.present ? data.attempts.value : this.attempts,
      lastError: data.lastError.present ? data.lastError.value : this.lastError,
      nextAttemptAt: data.nextAttemptAt.present
          ? data.nextAttemptAt.value
          : this.nextAttemptAt,
      createdAt: data.createdAt.present ? data.createdAt.value : this.createdAt,
      updatedAt: data.updatedAt.present ? data.updatedAt.value : this.updatedAt,
    );
  }

  @override
  String toString() {
    return (StringBuffer('PendingCommandRow(')
          ..write('id: $id, ')
          ..write('clientCommandId: $clientCommandId, ')
          ..write('orgId: $orgId, ')
          ..write('requestId: $requestId, ')
          ..write('type: $type, ')
          ..write('payloadJson: $payloadJson, ')
          ..write('status: $status, ')
          ..write('attempts: $attempts, ')
          ..write('lastError: $lastError, ')
          ..write('nextAttemptAt: $nextAttemptAt, ')
          ..write('createdAt: $createdAt, ')
          ..write('updatedAt: $updatedAt')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(
    id,
    clientCommandId,
    orgId,
    requestId,
    type,
    payloadJson,
    status,
    attempts,
    lastError,
    nextAttemptAt,
    createdAt,
    updatedAt,
  );
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is PendingCommandRow &&
          other.id == this.id &&
          other.clientCommandId == this.clientCommandId &&
          other.orgId == this.orgId &&
          other.requestId == this.requestId &&
          other.type == this.type &&
          other.payloadJson == this.payloadJson &&
          other.status == this.status &&
          other.attempts == this.attempts &&
          other.lastError == this.lastError &&
          other.nextAttemptAt == this.nextAttemptAt &&
          other.createdAt == this.createdAt &&
          other.updatedAt == this.updatedAt);
}

class PendingCommandsCompanion extends UpdateCompanion<PendingCommandRow> {
  final Value<int> id;
  final Value<String> clientCommandId;
  final Value<String> orgId;
  final Value<String> requestId;
  final Value<String> type;
  final Value<String> payloadJson;
  final Value<String> status;
  final Value<int> attempts;
  final Value<String?> lastError;
  final Value<DateTime?> nextAttemptAt;
  final Value<DateTime> createdAt;
  final Value<DateTime> updatedAt;
  const PendingCommandsCompanion({
    this.id = const Value.absent(),
    this.clientCommandId = const Value.absent(),
    this.orgId = const Value.absent(),
    this.requestId = const Value.absent(),
    this.type = const Value.absent(),
    this.payloadJson = const Value.absent(),
    this.status = const Value.absent(),
    this.attempts = const Value.absent(),
    this.lastError = const Value.absent(),
    this.nextAttemptAt = const Value.absent(),
    this.createdAt = const Value.absent(),
    this.updatedAt = const Value.absent(),
  });
  PendingCommandsCompanion.insert({
    this.id = const Value.absent(),
    required String clientCommandId,
    required String orgId,
    required String requestId,
    required String type,
    required String payloadJson,
    this.status = const Value.absent(),
    this.attempts = const Value.absent(),
    this.lastError = const Value.absent(),
    this.nextAttemptAt = const Value.absent(),
    required DateTime createdAt,
    required DateTime updatedAt,
  }) : clientCommandId = Value(clientCommandId),
       orgId = Value(orgId),
       requestId = Value(requestId),
       type = Value(type),
       payloadJson = Value(payloadJson),
       createdAt = Value(createdAt),
       updatedAt = Value(updatedAt);
  static Insertable<PendingCommandRow> custom({
    Expression<int>? id,
    Expression<String>? clientCommandId,
    Expression<String>? orgId,
    Expression<String>? requestId,
    Expression<String>? type,
    Expression<String>? payloadJson,
    Expression<String>? status,
    Expression<int>? attempts,
    Expression<String>? lastError,
    Expression<DateTime>? nextAttemptAt,
    Expression<DateTime>? createdAt,
    Expression<DateTime>? updatedAt,
  }) {
    return RawValuesInsertable({
      if (id != null) 'id': id,
      if (clientCommandId != null) 'client_command_id': clientCommandId,
      if (orgId != null) 'org_id': orgId,
      if (requestId != null) 'request_id': requestId,
      if (type != null) 'type': type,
      if (payloadJson != null) 'payload_json': payloadJson,
      if (status != null) 'status': status,
      if (attempts != null) 'attempts': attempts,
      if (lastError != null) 'last_error': lastError,
      if (nextAttemptAt != null) 'next_attempt_at': nextAttemptAt,
      if (createdAt != null) 'created_at': createdAt,
      if (updatedAt != null) 'updated_at': updatedAt,
    });
  }

  PendingCommandsCompanion copyWith({
    Value<int>? id,
    Value<String>? clientCommandId,
    Value<String>? orgId,
    Value<String>? requestId,
    Value<String>? type,
    Value<String>? payloadJson,
    Value<String>? status,
    Value<int>? attempts,
    Value<String?>? lastError,
    Value<DateTime?>? nextAttemptAt,
    Value<DateTime>? createdAt,
    Value<DateTime>? updatedAt,
  }) {
    return PendingCommandsCompanion(
      id: id ?? this.id,
      clientCommandId: clientCommandId ?? this.clientCommandId,
      orgId: orgId ?? this.orgId,
      requestId: requestId ?? this.requestId,
      type: type ?? this.type,
      payloadJson: payloadJson ?? this.payloadJson,
      status: status ?? this.status,
      attempts: attempts ?? this.attempts,
      lastError: lastError ?? this.lastError,
      nextAttemptAt: nextAttemptAt ?? this.nextAttemptAt,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (id.present) {
      map['id'] = Variable<int>(id.value);
    }
    if (clientCommandId.present) {
      map['client_command_id'] = Variable<String>(clientCommandId.value);
    }
    if (orgId.present) {
      map['org_id'] = Variable<String>(orgId.value);
    }
    if (requestId.present) {
      map['request_id'] = Variable<String>(requestId.value);
    }
    if (type.present) {
      map['type'] = Variable<String>(type.value);
    }
    if (payloadJson.present) {
      map['payload_json'] = Variable<String>(payloadJson.value);
    }
    if (status.present) {
      map['status'] = Variable<String>(status.value);
    }
    if (attempts.present) {
      map['attempts'] = Variable<int>(attempts.value);
    }
    if (lastError.present) {
      map['last_error'] = Variable<String>(lastError.value);
    }
    if (nextAttemptAt.present) {
      map['next_attempt_at'] = Variable<DateTime>(nextAttemptAt.value);
    }
    if (createdAt.present) {
      map['created_at'] = Variable<DateTime>(createdAt.value);
    }
    if (updatedAt.present) {
      map['updated_at'] = Variable<DateTime>(updatedAt.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('PendingCommandsCompanion(')
          ..write('id: $id, ')
          ..write('clientCommandId: $clientCommandId, ')
          ..write('orgId: $orgId, ')
          ..write('requestId: $requestId, ')
          ..write('type: $type, ')
          ..write('payloadJson: $payloadJson, ')
          ..write('status: $status, ')
          ..write('attempts: $attempts, ')
          ..write('lastError: $lastError, ')
          ..write('nextAttemptAt: $nextAttemptAt, ')
          ..write('createdAt: $createdAt, ')
          ..write('updatedAt: $updatedAt')
          ..write(')'))
        .toString();
  }
}

class $PendingAttachmentsTable extends PendingAttachments
    with TableInfo<$PendingAttachmentsTable, PendingAttachmentRow> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $PendingAttachmentsTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _idMeta = const VerificationMeta('id');
  @override
  late final GeneratedColumn<int> id = GeneratedColumn<int>(
    'id',
    aliasedName,
    false,
    hasAutoIncrement: true,
    type: DriftSqlType.int,
    requiredDuringInsert: false,
    defaultConstraints: GeneratedColumn.constraintIsAlways(
      'PRIMARY KEY AUTOINCREMENT',
    ),
  );
  static const VerificationMeta _clientCommandIdMeta = const VerificationMeta(
    'clientCommandId',
  );
  @override
  late final GeneratedColumn<String> clientCommandId = GeneratedColumn<String>(
    'client_command_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
    defaultConstraints: GeneratedColumn.constraintIsAlways(
      'REFERENCES pending_commands (client_command_id)',
    ),
  );
  static const VerificationMeta _positionMeta = const VerificationMeta(
    'position',
  );
  @override
  late final GeneratedColumn<int> position = GeneratedColumn<int>(
    'position',
    aliasedName,
    false,
    type: DriftSqlType.int,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _localPathMeta = const VerificationMeta(
    'localPath',
  );
  @override
  late final GeneratedColumn<String> localPath = GeneratedColumn<String>(
    'local_path',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _mimeTypeMeta = const VerificationMeta(
    'mimeType',
  );
  @override
  late final GeneratedColumn<String> mimeType = GeneratedColumn<String>(
    'mime_type',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _originalFilenameMeta = const VerificationMeta(
    'originalFilename',
  );
  @override
  late final GeneratedColumn<String> originalFilename = GeneratedColumn<String>(
    'original_filename',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _sizeBytesMeta = const VerificationMeta(
    'sizeBytes',
  );
  @override
  late final GeneratedColumn<int> sizeBytes = GeneratedColumn<int>(
    'size_bytes',
    aliasedName,
    false,
    type: DriftSqlType.int,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _statusMeta = const VerificationMeta('status');
  @override
  late final GeneratedColumn<String> status = GeneratedColumn<String>(
    'status',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
    defaultValue: const Constant('PENDING'),
  );
  static const VerificationMeta _uploadedFileIdMeta = const VerificationMeta(
    'uploadedFileId',
  );
  @override
  late final GeneratedColumn<String> uploadedFileId = GeneratedColumn<String>(
    'uploaded_file_id',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  @override
  List<GeneratedColumn> get $columns => [
    id,
    clientCommandId,
    position,
    localPath,
    mimeType,
    originalFilename,
    sizeBytes,
    status,
    uploadedFileId,
  ];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'pending_attachments';
  @override
  VerificationContext validateIntegrity(
    Insertable<PendingAttachmentRow> instance, {
    bool isInserting = false,
  }) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('id')) {
      context.handle(_idMeta, id.isAcceptableOrUnknown(data['id']!, _idMeta));
    }
    if (data.containsKey('client_command_id')) {
      context.handle(
        _clientCommandIdMeta,
        clientCommandId.isAcceptableOrUnknown(
          data['client_command_id']!,
          _clientCommandIdMeta,
        ),
      );
    } else if (isInserting) {
      context.missing(_clientCommandIdMeta);
    }
    if (data.containsKey('position')) {
      context.handle(
        _positionMeta,
        position.isAcceptableOrUnknown(data['position']!, _positionMeta),
      );
    } else if (isInserting) {
      context.missing(_positionMeta);
    }
    if (data.containsKey('local_path')) {
      context.handle(
        _localPathMeta,
        localPath.isAcceptableOrUnknown(data['local_path']!, _localPathMeta),
      );
    } else if (isInserting) {
      context.missing(_localPathMeta);
    }
    if (data.containsKey('mime_type')) {
      context.handle(
        _mimeTypeMeta,
        mimeType.isAcceptableOrUnknown(data['mime_type']!, _mimeTypeMeta),
      );
    } else if (isInserting) {
      context.missing(_mimeTypeMeta);
    }
    if (data.containsKey('original_filename')) {
      context.handle(
        _originalFilenameMeta,
        originalFilename.isAcceptableOrUnknown(
          data['original_filename']!,
          _originalFilenameMeta,
        ),
      );
    } else if (isInserting) {
      context.missing(_originalFilenameMeta);
    }
    if (data.containsKey('size_bytes')) {
      context.handle(
        _sizeBytesMeta,
        sizeBytes.isAcceptableOrUnknown(data['size_bytes']!, _sizeBytesMeta),
      );
    } else if (isInserting) {
      context.missing(_sizeBytesMeta);
    }
    if (data.containsKey('status')) {
      context.handle(
        _statusMeta,
        status.isAcceptableOrUnknown(data['status']!, _statusMeta),
      );
    }
    if (data.containsKey('uploaded_file_id')) {
      context.handle(
        _uploadedFileIdMeta,
        uploadedFileId.isAcceptableOrUnknown(
          data['uploaded_file_id']!,
          _uploadedFileIdMeta,
        ),
      );
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {id};
  @override
  List<Set<GeneratedColumn>> get uniqueKeys => [
    {clientCommandId, position},
  ];
  @override
  PendingAttachmentRow map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return PendingAttachmentRow(
      id: attachedDatabase.typeMapping.read(
        DriftSqlType.int,
        data['${effectivePrefix}id'],
      )!,
      clientCommandId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}client_command_id'],
      )!,
      position: attachedDatabase.typeMapping.read(
        DriftSqlType.int,
        data['${effectivePrefix}position'],
      )!,
      localPath: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}local_path'],
      )!,
      mimeType: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}mime_type'],
      )!,
      originalFilename: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}original_filename'],
      )!,
      sizeBytes: attachedDatabase.typeMapping.read(
        DriftSqlType.int,
        data['${effectivePrefix}size_bytes'],
      )!,
      status: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}status'],
      )!,
      uploadedFileId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}uploaded_file_id'],
      ),
    );
  }

  @override
  $PendingAttachmentsTable createAlias(String alias) {
    return $PendingAttachmentsTable(attachedDatabase, alias);
  }
}

class PendingAttachmentRow extends DataClass
    implements Insertable<PendingAttachmentRow> {
  final int id;
  final String clientCommandId;
  final int position;
  final String localPath;
  final String mimeType;
  final String originalFilename;
  final int sizeBytes;
  final String status;
  final String? uploadedFileId;
  const PendingAttachmentRow({
    required this.id,
    required this.clientCommandId,
    required this.position,
    required this.localPath,
    required this.mimeType,
    required this.originalFilename,
    required this.sizeBytes,
    required this.status,
    this.uploadedFileId,
  });
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['id'] = Variable<int>(id);
    map['client_command_id'] = Variable<String>(clientCommandId);
    map['position'] = Variable<int>(position);
    map['local_path'] = Variable<String>(localPath);
    map['mime_type'] = Variable<String>(mimeType);
    map['original_filename'] = Variable<String>(originalFilename);
    map['size_bytes'] = Variable<int>(sizeBytes);
    map['status'] = Variable<String>(status);
    if (!nullToAbsent || uploadedFileId != null) {
      map['uploaded_file_id'] = Variable<String>(uploadedFileId);
    }
    return map;
  }

  PendingAttachmentsCompanion toCompanion(bool nullToAbsent) {
    return PendingAttachmentsCompanion(
      id: Value(id),
      clientCommandId: Value(clientCommandId),
      position: Value(position),
      localPath: Value(localPath),
      mimeType: Value(mimeType),
      originalFilename: Value(originalFilename),
      sizeBytes: Value(sizeBytes),
      status: Value(status),
      uploadedFileId: uploadedFileId == null && nullToAbsent
          ? const Value.absent()
          : Value(uploadedFileId),
    );
  }

  factory PendingAttachmentRow.fromJson(
    Map<String, dynamic> json, {
    ValueSerializer? serializer,
  }) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return PendingAttachmentRow(
      id: serializer.fromJson<int>(json['id']),
      clientCommandId: serializer.fromJson<String>(json['clientCommandId']),
      position: serializer.fromJson<int>(json['position']),
      localPath: serializer.fromJson<String>(json['localPath']),
      mimeType: serializer.fromJson<String>(json['mimeType']),
      originalFilename: serializer.fromJson<String>(json['originalFilename']),
      sizeBytes: serializer.fromJson<int>(json['sizeBytes']),
      status: serializer.fromJson<String>(json['status']),
      uploadedFileId: serializer.fromJson<String?>(json['uploadedFileId']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'id': serializer.toJson<int>(id),
      'clientCommandId': serializer.toJson<String>(clientCommandId),
      'position': serializer.toJson<int>(position),
      'localPath': serializer.toJson<String>(localPath),
      'mimeType': serializer.toJson<String>(mimeType),
      'originalFilename': serializer.toJson<String>(originalFilename),
      'sizeBytes': serializer.toJson<int>(sizeBytes),
      'status': serializer.toJson<String>(status),
      'uploadedFileId': serializer.toJson<String?>(uploadedFileId),
    };
  }

  PendingAttachmentRow copyWith({
    int? id,
    String? clientCommandId,
    int? position,
    String? localPath,
    String? mimeType,
    String? originalFilename,
    int? sizeBytes,
    String? status,
    Value<String?> uploadedFileId = const Value.absent(),
  }) => PendingAttachmentRow(
    id: id ?? this.id,
    clientCommandId: clientCommandId ?? this.clientCommandId,
    position: position ?? this.position,
    localPath: localPath ?? this.localPath,
    mimeType: mimeType ?? this.mimeType,
    originalFilename: originalFilename ?? this.originalFilename,
    sizeBytes: sizeBytes ?? this.sizeBytes,
    status: status ?? this.status,
    uploadedFileId: uploadedFileId.present
        ? uploadedFileId.value
        : this.uploadedFileId,
  );
  PendingAttachmentRow copyWithCompanion(PendingAttachmentsCompanion data) {
    return PendingAttachmentRow(
      id: data.id.present ? data.id.value : this.id,
      clientCommandId: data.clientCommandId.present
          ? data.clientCommandId.value
          : this.clientCommandId,
      position: data.position.present ? data.position.value : this.position,
      localPath: data.localPath.present ? data.localPath.value : this.localPath,
      mimeType: data.mimeType.present ? data.mimeType.value : this.mimeType,
      originalFilename: data.originalFilename.present
          ? data.originalFilename.value
          : this.originalFilename,
      sizeBytes: data.sizeBytes.present ? data.sizeBytes.value : this.sizeBytes,
      status: data.status.present ? data.status.value : this.status,
      uploadedFileId: data.uploadedFileId.present
          ? data.uploadedFileId.value
          : this.uploadedFileId,
    );
  }

  @override
  String toString() {
    return (StringBuffer('PendingAttachmentRow(')
          ..write('id: $id, ')
          ..write('clientCommandId: $clientCommandId, ')
          ..write('position: $position, ')
          ..write('localPath: $localPath, ')
          ..write('mimeType: $mimeType, ')
          ..write('originalFilename: $originalFilename, ')
          ..write('sizeBytes: $sizeBytes, ')
          ..write('status: $status, ')
          ..write('uploadedFileId: $uploadedFileId')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(
    id,
    clientCommandId,
    position,
    localPath,
    mimeType,
    originalFilename,
    sizeBytes,
    status,
    uploadedFileId,
  );
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is PendingAttachmentRow &&
          other.id == this.id &&
          other.clientCommandId == this.clientCommandId &&
          other.position == this.position &&
          other.localPath == this.localPath &&
          other.mimeType == this.mimeType &&
          other.originalFilename == this.originalFilename &&
          other.sizeBytes == this.sizeBytes &&
          other.status == this.status &&
          other.uploadedFileId == this.uploadedFileId);
}

class PendingAttachmentsCompanion
    extends UpdateCompanion<PendingAttachmentRow> {
  final Value<int> id;
  final Value<String> clientCommandId;
  final Value<int> position;
  final Value<String> localPath;
  final Value<String> mimeType;
  final Value<String> originalFilename;
  final Value<int> sizeBytes;
  final Value<String> status;
  final Value<String?> uploadedFileId;
  const PendingAttachmentsCompanion({
    this.id = const Value.absent(),
    this.clientCommandId = const Value.absent(),
    this.position = const Value.absent(),
    this.localPath = const Value.absent(),
    this.mimeType = const Value.absent(),
    this.originalFilename = const Value.absent(),
    this.sizeBytes = const Value.absent(),
    this.status = const Value.absent(),
    this.uploadedFileId = const Value.absent(),
  });
  PendingAttachmentsCompanion.insert({
    this.id = const Value.absent(),
    required String clientCommandId,
    required int position,
    required String localPath,
    required String mimeType,
    required String originalFilename,
    required int sizeBytes,
    this.status = const Value.absent(),
    this.uploadedFileId = const Value.absent(),
  }) : clientCommandId = Value(clientCommandId),
       position = Value(position),
       localPath = Value(localPath),
       mimeType = Value(mimeType),
       originalFilename = Value(originalFilename),
       sizeBytes = Value(sizeBytes);
  static Insertable<PendingAttachmentRow> custom({
    Expression<int>? id,
    Expression<String>? clientCommandId,
    Expression<int>? position,
    Expression<String>? localPath,
    Expression<String>? mimeType,
    Expression<String>? originalFilename,
    Expression<int>? sizeBytes,
    Expression<String>? status,
    Expression<String>? uploadedFileId,
  }) {
    return RawValuesInsertable({
      if (id != null) 'id': id,
      if (clientCommandId != null) 'client_command_id': clientCommandId,
      if (position != null) 'position': position,
      if (localPath != null) 'local_path': localPath,
      if (mimeType != null) 'mime_type': mimeType,
      if (originalFilename != null) 'original_filename': originalFilename,
      if (sizeBytes != null) 'size_bytes': sizeBytes,
      if (status != null) 'status': status,
      if (uploadedFileId != null) 'uploaded_file_id': uploadedFileId,
    });
  }

  PendingAttachmentsCompanion copyWith({
    Value<int>? id,
    Value<String>? clientCommandId,
    Value<int>? position,
    Value<String>? localPath,
    Value<String>? mimeType,
    Value<String>? originalFilename,
    Value<int>? sizeBytes,
    Value<String>? status,
    Value<String?>? uploadedFileId,
  }) {
    return PendingAttachmentsCompanion(
      id: id ?? this.id,
      clientCommandId: clientCommandId ?? this.clientCommandId,
      position: position ?? this.position,
      localPath: localPath ?? this.localPath,
      mimeType: mimeType ?? this.mimeType,
      originalFilename: originalFilename ?? this.originalFilename,
      sizeBytes: sizeBytes ?? this.sizeBytes,
      status: status ?? this.status,
      uploadedFileId: uploadedFileId ?? this.uploadedFileId,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (id.present) {
      map['id'] = Variable<int>(id.value);
    }
    if (clientCommandId.present) {
      map['client_command_id'] = Variable<String>(clientCommandId.value);
    }
    if (position.present) {
      map['position'] = Variable<int>(position.value);
    }
    if (localPath.present) {
      map['local_path'] = Variable<String>(localPath.value);
    }
    if (mimeType.present) {
      map['mime_type'] = Variable<String>(mimeType.value);
    }
    if (originalFilename.present) {
      map['original_filename'] = Variable<String>(originalFilename.value);
    }
    if (sizeBytes.present) {
      map['size_bytes'] = Variable<int>(sizeBytes.value);
    }
    if (status.present) {
      map['status'] = Variable<String>(status.value);
    }
    if (uploadedFileId.present) {
      map['uploaded_file_id'] = Variable<String>(uploadedFileId.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('PendingAttachmentsCompanion(')
          ..write('id: $id, ')
          ..write('clientCommandId: $clientCommandId, ')
          ..write('position: $position, ')
          ..write('localPath: $localPath, ')
          ..write('mimeType: $mimeType, ')
          ..write('originalFilename: $originalFilename, ')
          ..write('sizeBytes: $sizeBytes, ')
          ..write('status: $status, ')
          ..write('uploadedFileId: $uploadedFileId')
          ..write(')'))
        .toString();
  }
}

abstract class _$AppDatabase extends GeneratedDatabase {
  _$AppDatabase(QueryExecutor e) : super(e);
  $AppDatabaseManager get managers => $AppDatabaseManager(this);
  late final $SessionTableTable sessionTable = $SessionTableTable(this);
  late final $CachedJobsTable cachedJobs = $CachedJobsTable(this);
  late final $PendingCommandsTable pendingCommands = $PendingCommandsTable(
    this,
  );
  late final $PendingAttachmentsTable pendingAttachments =
      $PendingAttachmentsTable(this);
  @override
  Iterable<TableInfo<Table, Object?>> get allTables =>
      allSchemaEntities.whereType<TableInfo<Table, Object?>>();
  @override
  List<DatabaseSchemaEntity> get allSchemaEntities => [
    sessionTable,
    cachedJobs,
    pendingCommands,
    pendingAttachments,
  ];
}

typedef $$SessionTableTableCreateCompanionBuilder =
    SessionTableCompanion Function({
      Value<int> id,
      required String userId,
      required String email,
      required String fullName,
      required String membershipsJson,
      Value<String?> selectedOrgId,
      Value<DateTime?> expiresAt,
      required DateTime updatedAt,
    });
typedef $$SessionTableTableUpdateCompanionBuilder =
    SessionTableCompanion Function({
      Value<int> id,
      Value<String> userId,
      Value<String> email,
      Value<String> fullName,
      Value<String> membershipsJson,
      Value<String?> selectedOrgId,
      Value<DateTime?> expiresAt,
      Value<DateTime> updatedAt,
    });

class $$SessionTableTableFilterComposer
    extends Composer<_$AppDatabase, $SessionTableTable> {
  $$SessionTableTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<int> get id => $composableBuilder(
    column: $table.id,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get userId => $composableBuilder(
    column: $table.userId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get email => $composableBuilder(
    column: $table.email,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get fullName => $composableBuilder(
    column: $table.fullName,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get membershipsJson => $composableBuilder(
    column: $table.membershipsJson,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get selectedOrgId => $composableBuilder(
    column: $table.selectedOrgId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<DateTime> get expiresAt => $composableBuilder(
    column: $table.expiresAt,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<DateTime> get updatedAt => $composableBuilder(
    column: $table.updatedAt,
    builder: (column) => ColumnFilters(column),
  );
}

class $$SessionTableTableOrderingComposer
    extends Composer<_$AppDatabase, $SessionTableTable> {
  $$SessionTableTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<int> get id => $composableBuilder(
    column: $table.id,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get userId => $composableBuilder(
    column: $table.userId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get email => $composableBuilder(
    column: $table.email,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get fullName => $composableBuilder(
    column: $table.fullName,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get membershipsJson => $composableBuilder(
    column: $table.membershipsJson,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get selectedOrgId => $composableBuilder(
    column: $table.selectedOrgId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<DateTime> get expiresAt => $composableBuilder(
    column: $table.expiresAt,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<DateTime> get updatedAt => $composableBuilder(
    column: $table.updatedAt,
    builder: (column) => ColumnOrderings(column),
  );
}

class $$SessionTableTableAnnotationComposer
    extends Composer<_$AppDatabase, $SessionTableTable> {
  $$SessionTableTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<int> get id =>
      $composableBuilder(column: $table.id, builder: (column) => column);

  GeneratedColumn<String> get userId =>
      $composableBuilder(column: $table.userId, builder: (column) => column);

  GeneratedColumn<String> get email =>
      $composableBuilder(column: $table.email, builder: (column) => column);

  GeneratedColumn<String> get fullName =>
      $composableBuilder(column: $table.fullName, builder: (column) => column);

  GeneratedColumn<String> get membershipsJson => $composableBuilder(
    column: $table.membershipsJson,
    builder: (column) => column,
  );

  GeneratedColumn<String> get selectedOrgId => $composableBuilder(
    column: $table.selectedOrgId,
    builder: (column) => column,
  );

  GeneratedColumn<DateTime> get expiresAt =>
      $composableBuilder(column: $table.expiresAt, builder: (column) => column);

  GeneratedColumn<DateTime> get updatedAt =>
      $composableBuilder(column: $table.updatedAt, builder: (column) => column);
}

class $$SessionTableTableTableManager
    extends
        RootTableManager<
          _$AppDatabase,
          $SessionTableTable,
          SessionRow,
          $$SessionTableTableFilterComposer,
          $$SessionTableTableOrderingComposer,
          $$SessionTableTableAnnotationComposer,
          $$SessionTableTableCreateCompanionBuilder,
          $$SessionTableTableUpdateCompanionBuilder,
          (
            SessionRow,
            BaseReferences<_$AppDatabase, $SessionTableTable, SessionRow>,
          ),
          SessionRow,
          PrefetchHooks Function()
        > {
  $$SessionTableTableTableManager(_$AppDatabase db, $SessionTableTable table)
    : super(
        TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$SessionTableTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$SessionTableTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$SessionTableTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback:
              ({
                Value<int> id = const Value.absent(),
                Value<String> userId = const Value.absent(),
                Value<String> email = const Value.absent(),
                Value<String> fullName = const Value.absent(),
                Value<String> membershipsJson = const Value.absent(),
                Value<String?> selectedOrgId = const Value.absent(),
                Value<DateTime?> expiresAt = const Value.absent(),
                Value<DateTime> updatedAt = const Value.absent(),
              }) => SessionTableCompanion(
                id: id,
                userId: userId,
                email: email,
                fullName: fullName,
                membershipsJson: membershipsJson,
                selectedOrgId: selectedOrgId,
                expiresAt: expiresAt,
                updatedAt: updatedAt,
              ),
          createCompanionCallback:
              ({
                Value<int> id = const Value.absent(),
                required String userId,
                required String email,
                required String fullName,
                required String membershipsJson,
                Value<String?> selectedOrgId = const Value.absent(),
                Value<DateTime?> expiresAt = const Value.absent(),
                required DateTime updatedAt,
              }) => SessionTableCompanion.insert(
                id: id,
                userId: userId,
                email: email,
                fullName: fullName,
                membershipsJson: membershipsJson,
                selectedOrgId: selectedOrgId,
                expiresAt: expiresAt,
                updatedAt: updatedAt,
              ),
          withReferenceMapper: (p0) => p0
              .map(
                (e) => (
                  e.readTable<$SessionTableTable, SessionRow>(table),
                  BaseReferences<_$AppDatabase, $SessionTableTable, SessionRow>(
                    db,
                    table,
                    e,
                  ),
                ),
              )
              .toList(),
          prefetchHooksCallback: null,
        ),
      );
}

typedef $$SessionTableTableProcessedTableManager =
    ProcessedTableManager<
      _$AppDatabase,
      $SessionTableTable,
      SessionRow,
      $$SessionTableTableFilterComposer,
      $$SessionTableTableOrderingComposer,
      $$SessionTableTableAnnotationComposer,
      $$SessionTableTableCreateCompanionBuilder,
      $$SessionTableTableUpdateCompanionBuilder,
      (
        SessionRow,
        BaseReferences<_$AppDatabase, $SessionTableTable, SessionRow>,
      ),
      SessionRow,
      PrefetchHooks Function()
    >;
typedef $$CachedJobsTableCreateCompanionBuilder = CachedJobsCompanion Function({
  required String orgId,
  required String requestId,
  Value<String?> assignmentId,
  Value<String?> scope,
  Value<String?> itemJson,
  Value<String?> detailJson,
  required DateTime fetchedAt,
  Value<int> rowid,
});
typedef $$CachedJobsTableUpdateCompanionBuilder = CachedJobsCompanion Function({
  Value<String> orgId,
  Value<String> requestId,
  Value<String?> assignmentId,
  Value<String?> scope,
  Value<String?> itemJson,
  Value<String?> detailJson,
  Value<DateTime> fetchedAt,
  Value<int> rowid,
});

class $$CachedJobsTableFilterComposer
    extends Composer<_$AppDatabase, $CachedJobsTable> {
  $$CachedJobsTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<String> get orgId => $composableBuilder(
    column: $table.orgId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get requestId => $composableBuilder(
    column: $table.requestId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get assignmentId => $composableBuilder(
    column: $table.assignmentId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get scope => $composableBuilder(
    column: $table.scope,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get itemJson => $composableBuilder(
    column: $table.itemJson,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get detailJson => $composableBuilder(
    column: $table.detailJson,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<DateTime> get fetchedAt => $composableBuilder(
    column: $table.fetchedAt,
    builder: (column) => ColumnFilters(column),
  );
}

class $$CachedJobsTableOrderingComposer
    extends Composer<_$AppDatabase, $CachedJobsTable> {
  $$CachedJobsTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<String> get orgId => $composableBuilder(
    column: $table.orgId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get requestId => $composableBuilder(
    column: $table.requestId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get assignmentId => $composableBuilder(
    column: $table.assignmentId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get scope => $composableBuilder(
    column: $table.scope,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get itemJson => $composableBuilder(
    column: $table.itemJson,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get detailJson => $composableBuilder(
    column: $table.detailJson,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<DateTime> get fetchedAt => $composableBuilder(
    column: $table.fetchedAt,
    builder: (column) => ColumnOrderings(column),
  );
}

class $$CachedJobsTableAnnotationComposer
    extends Composer<_$AppDatabase, $CachedJobsTable> {
  $$CachedJobsTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<String> get orgId =>
      $composableBuilder(column: $table.orgId, builder: (column) => column);

  GeneratedColumn<String> get requestId =>
      $composableBuilder(column: $table.requestId, builder: (column) => column);

  GeneratedColumn<String> get assignmentId => $composableBuilder(
    column: $table.assignmentId,
    builder: (column) => column,
  );

  GeneratedColumn<String> get scope =>
      $composableBuilder(column: $table.scope, builder: (column) => column);

  GeneratedColumn<String> get itemJson =>
      $composableBuilder(column: $table.itemJson, builder: (column) => column);

  GeneratedColumn<String> get detailJson => $composableBuilder(
    column: $table.detailJson,
    builder: (column) => column,
  );

  GeneratedColumn<DateTime> get fetchedAt =>
      $composableBuilder(column: $table.fetchedAt, builder: (column) => column);
}

class $$CachedJobsTableTableManager
    extends
        RootTableManager<
          _$AppDatabase,
          $CachedJobsTable,
          CachedJobRow,
          $$CachedJobsTableFilterComposer,
          $$CachedJobsTableOrderingComposer,
          $$CachedJobsTableAnnotationComposer,
          $$CachedJobsTableCreateCompanionBuilder,
          $$CachedJobsTableUpdateCompanionBuilder,
          (
            CachedJobRow,
            BaseReferences<_$AppDatabase, $CachedJobsTable, CachedJobRow>,
          ),
          CachedJobRow,
          PrefetchHooks Function()
        > {
  $$CachedJobsTableTableManager(_$AppDatabase db, $CachedJobsTable table)
    : super(
        TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$CachedJobsTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$CachedJobsTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$CachedJobsTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback:
              ({
                Value<String> orgId = const Value.absent(),
                Value<String> requestId = const Value.absent(),
                Value<String?> assignmentId = const Value.absent(),
                Value<String?> scope = const Value.absent(),
                Value<String?> itemJson = const Value.absent(),
                Value<String?> detailJson = const Value.absent(),
                Value<DateTime> fetchedAt = const Value.absent(),
                Value<int> rowid = const Value.absent(),
              }) => CachedJobsCompanion(
                orgId: orgId,
                requestId: requestId,
                assignmentId: assignmentId,
                scope: scope,
                itemJson: itemJson,
                detailJson: detailJson,
                fetchedAt: fetchedAt,
                rowid: rowid,
              ),
          createCompanionCallback:
              ({
                required String orgId,
                required String requestId,
                Value<String?> assignmentId = const Value.absent(),
                Value<String?> scope = const Value.absent(),
                Value<String?> itemJson = const Value.absent(),
                Value<String?> detailJson = const Value.absent(),
                required DateTime fetchedAt,
                Value<int> rowid = const Value.absent(),
              }) => CachedJobsCompanion.insert(
                orgId: orgId,
                requestId: requestId,
                assignmentId: assignmentId,
                scope: scope,
                itemJson: itemJson,
                detailJson: detailJson,
                fetchedAt: fetchedAt,
                rowid: rowid,
              ),
          withReferenceMapper: (p0) => p0
              .map(
                (e) => (
                  e.readTable<$CachedJobsTable, CachedJobRow>(table),
                  BaseReferences<_$AppDatabase, $CachedJobsTable, CachedJobRow>(
                    db,
                    table,
                    e,
                  ),
                ),
              )
              .toList(),
          prefetchHooksCallback: null,
        ),
      );
}

typedef $$CachedJobsTableProcessedTableManager =
    ProcessedTableManager<
      _$AppDatabase,
      $CachedJobsTable,
      CachedJobRow,
      $$CachedJobsTableFilterComposer,
      $$CachedJobsTableOrderingComposer,
      $$CachedJobsTableAnnotationComposer,
      $$CachedJobsTableCreateCompanionBuilder,
      $$CachedJobsTableUpdateCompanionBuilder,
      (
        CachedJobRow,
        BaseReferences<_$AppDatabase, $CachedJobsTable, CachedJobRow>,
      ),
      CachedJobRow,
      PrefetchHooks Function()
    >;
typedef $$PendingCommandsTableCreateCompanionBuilder =
    PendingCommandsCompanion Function({
      Value<int> id,
      required String clientCommandId,
      required String orgId,
      required String requestId,
      required String type,
      required String payloadJson,
      Value<String> status,
      Value<int> attempts,
      Value<String?> lastError,
      Value<DateTime?> nextAttemptAt,
      required DateTime createdAt,
      required DateTime updatedAt,
    });
typedef $$PendingCommandsTableUpdateCompanionBuilder =
    PendingCommandsCompanion Function({
      Value<int> id,
      Value<String> clientCommandId,
      Value<String> orgId,
      Value<String> requestId,
      Value<String> type,
      Value<String> payloadJson,
      Value<String> status,
      Value<int> attempts,
      Value<String?> lastError,
      Value<DateTime?> nextAttemptAt,
      Value<DateTime> createdAt,
      Value<DateTime> updatedAt,
    });

final class $$PendingCommandsTableReferences
    extends
        BaseReferences<
          _$AppDatabase,
          $PendingCommandsTable,
          PendingCommandRow
        > {
  $$PendingCommandsTableReferences(
    super.$_db,
    super.$_table,
    super.$_typedResult,
  );

  static MultiTypedResultKey<
    $PendingAttachmentsTable,
    List<PendingAttachmentRow>
  >
  _pendingAttachmentsRefsTable(_$AppDatabase db) =>
      MultiTypedResultKey.fromTable(
        db.pendingAttachments,
        aliasName: 'pending_commands__client_command_id__pending_attachments__client_command_id',
      );

  $$PendingAttachmentsTableProcessedTableManager get pendingAttachmentsRefs {
    final manager =
        $$PendingAttachmentsTableTableManager(
          $_db,
          $_db.pendingAttachments,
        ).filter(
          (f) => f.clientCommandId.clientCommandId.sqlEquals(
            $_itemColumn<String>('client_command_id')!,
          ),
        );

    final cache = $_typedResult.readTableOrNull(
      _pendingAttachmentsRefsTable($_db),
    );
    return ProcessedTableManager(
      manager.$state.copyWith(prefetchedData: cache),
    );
  }
}

class $$PendingCommandsTableFilterComposer
    extends Composer<_$AppDatabase, $PendingCommandsTable> {
  $$PendingCommandsTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<int> get id => $composableBuilder(
    column: $table.id,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get clientCommandId => $composableBuilder(
    column: $table.clientCommandId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get orgId => $composableBuilder(
    column: $table.orgId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get requestId => $composableBuilder(
    column: $table.requestId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get type => $composableBuilder(
    column: $table.type,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get payloadJson => $composableBuilder(
    column: $table.payloadJson,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get status => $composableBuilder(
    column: $table.status,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<int> get attempts => $composableBuilder(
    column: $table.attempts,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get lastError => $composableBuilder(
    column: $table.lastError,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<DateTime> get nextAttemptAt => $composableBuilder(
    column: $table.nextAttemptAt,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<DateTime> get createdAt => $composableBuilder(
    column: $table.createdAt,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<DateTime> get updatedAt => $composableBuilder(
    column: $table.updatedAt,
    builder: (column) => ColumnFilters(column),
  );

  Expression<bool> pendingAttachmentsRefs(
    Expression<bool> Function($$PendingAttachmentsTableFilterComposer f) f,
  ) {
    final $$PendingAttachmentsTableFilterComposer composer = $composerBuilder(
      composer: this,
      getCurrentColumn: (t) => t.clientCommandId,
      referencedTable: $db.pendingAttachments,
      getReferencedColumn: (t) => t.clientCommandId,
      builder:
          (
            joinBuilder, {
            $addJoinBuilderToRootComposer,
            $removeJoinBuilderFromRootComposer,
          }) => $$PendingAttachmentsTableFilterComposer(
            $db: $db,
            $table: $db.pendingAttachments,
            $addJoinBuilderToRootComposer: $addJoinBuilderToRootComposer,
            joinBuilder: joinBuilder,
            $removeJoinBuilderFromRootComposer:
                $removeJoinBuilderFromRootComposer,
          ),
    );
    return f(composer);
  }
}

class $$PendingCommandsTableOrderingComposer
    extends Composer<_$AppDatabase, $PendingCommandsTable> {
  $$PendingCommandsTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<int> get id => $composableBuilder(
    column: $table.id,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get clientCommandId => $composableBuilder(
    column: $table.clientCommandId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get orgId => $composableBuilder(
    column: $table.orgId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get requestId => $composableBuilder(
    column: $table.requestId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get type => $composableBuilder(
    column: $table.type,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get payloadJson => $composableBuilder(
    column: $table.payloadJson,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get status => $composableBuilder(
    column: $table.status,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<int> get attempts => $composableBuilder(
    column: $table.attempts,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get lastError => $composableBuilder(
    column: $table.lastError,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<DateTime> get nextAttemptAt => $composableBuilder(
    column: $table.nextAttemptAt,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<DateTime> get createdAt => $composableBuilder(
    column: $table.createdAt,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<DateTime> get updatedAt => $composableBuilder(
    column: $table.updatedAt,
    builder: (column) => ColumnOrderings(column),
  );
}

class $$PendingCommandsTableAnnotationComposer
    extends Composer<_$AppDatabase, $PendingCommandsTable> {
  $$PendingCommandsTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<int> get id =>
      $composableBuilder(column: $table.id, builder: (column) => column);

  GeneratedColumn<String> get clientCommandId => $composableBuilder(
    column: $table.clientCommandId,
    builder: (column) => column,
  );

  GeneratedColumn<String> get orgId =>
      $composableBuilder(column: $table.orgId, builder: (column) => column);

  GeneratedColumn<String> get requestId =>
      $composableBuilder(column: $table.requestId, builder: (column) => column);

  GeneratedColumn<String> get type =>
      $composableBuilder(column: $table.type, builder: (column) => column);

  GeneratedColumn<String> get payloadJson => $composableBuilder(
    column: $table.payloadJson,
    builder: (column) => column,
  );

  GeneratedColumn<String> get status =>
      $composableBuilder(column: $table.status, builder: (column) => column);

  GeneratedColumn<int> get attempts =>
      $composableBuilder(column: $table.attempts, builder: (column) => column);

  GeneratedColumn<String> get lastError =>
      $composableBuilder(column: $table.lastError, builder: (column) => column);

  GeneratedColumn<DateTime> get nextAttemptAt => $composableBuilder(
    column: $table.nextAttemptAt,
    builder: (column) => column,
  );

  GeneratedColumn<DateTime> get createdAt =>
      $composableBuilder(column: $table.createdAt, builder: (column) => column);

  GeneratedColumn<DateTime> get updatedAt =>
      $composableBuilder(column: $table.updatedAt, builder: (column) => column);

  Expression<T> pendingAttachmentsRefs<T extends Object>(
    Expression<T> Function($$PendingAttachmentsTableAnnotationComposer a) f,
  ) {
    final $$PendingAttachmentsTableAnnotationComposer composer =
        $composerBuilder(
          composer: this,
          getCurrentColumn: (t) => t.clientCommandId,
          referencedTable: $db.pendingAttachments,
          getReferencedColumn: (t) => t.clientCommandId,
          builder:
              (
                joinBuilder, {
                $addJoinBuilderToRootComposer,
                $removeJoinBuilderFromRootComposer,
              }) => $$PendingAttachmentsTableAnnotationComposer(
                $db: $db,
                $table: $db.pendingAttachments,
                $addJoinBuilderToRootComposer: $addJoinBuilderToRootComposer,
                joinBuilder: joinBuilder,
                $removeJoinBuilderFromRootComposer:
                    $removeJoinBuilderFromRootComposer,
              ),
        );
    return f(composer);
  }
}

class $$PendingCommandsTableTableManager
    extends
        RootTableManager<
          _$AppDatabase,
          $PendingCommandsTable,
          PendingCommandRow,
          $$PendingCommandsTableFilterComposer,
          $$PendingCommandsTableOrderingComposer,
          $$PendingCommandsTableAnnotationComposer,
          $$PendingCommandsTableCreateCompanionBuilder,
          $$PendingCommandsTableUpdateCompanionBuilder,
          (PendingCommandRow, $$PendingCommandsTableReferences),
          PendingCommandRow,
          PrefetchHooks Function({bool pendingAttachmentsRefs})
        > {
  $$PendingCommandsTableTableManager(
    _$AppDatabase db,
    $PendingCommandsTable table,
  ) : super(
        TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$PendingCommandsTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$PendingCommandsTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$PendingCommandsTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback:
              ({
                Value<int> id = const Value.absent(),
                Value<String> clientCommandId = const Value.absent(),
                Value<String> orgId = const Value.absent(),
                Value<String> requestId = const Value.absent(),
                Value<String> type = const Value.absent(),
                Value<String> payloadJson = const Value.absent(),
                Value<String> status = const Value.absent(),
                Value<int> attempts = const Value.absent(),
                Value<String?> lastError = const Value.absent(),
                Value<DateTime?> nextAttemptAt = const Value.absent(),
                Value<DateTime> createdAt = const Value.absent(),
                Value<DateTime> updatedAt = const Value.absent(),
              }) => PendingCommandsCompanion(
                id: id,
                clientCommandId: clientCommandId,
                orgId: orgId,
                requestId: requestId,
                type: type,
                payloadJson: payloadJson,
                status: status,
                attempts: attempts,
                lastError: lastError,
                nextAttemptAt: nextAttemptAt,
                createdAt: createdAt,
                updatedAt: updatedAt,
              ),
          createCompanionCallback:
              ({
                Value<int> id = const Value.absent(),
                required String clientCommandId,
                required String orgId,
                required String requestId,
                required String type,
                required String payloadJson,
                Value<String> status = const Value.absent(),
                Value<int> attempts = const Value.absent(),
                Value<String?> lastError = const Value.absent(),
                Value<DateTime?> nextAttemptAt = const Value.absent(),
                required DateTime createdAt,
                required DateTime updatedAt,
              }) => PendingCommandsCompanion.insert(
                id: id,
                clientCommandId: clientCommandId,
                orgId: orgId,
                requestId: requestId,
                type: type,
                payloadJson: payloadJson,
                status: status,
                attempts: attempts,
                lastError: lastError,
                nextAttemptAt: nextAttemptAt,
                createdAt: createdAt,
                updatedAt: updatedAt,
              ),
          withReferenceMapper: (p0) => p0
              .map(
                (e) => (
                  e.readTable<$PendingCommandsTable, PendingCommandRow>(table),
                  $$PendingCommandsTableReferences(db, table, e),
                ),
              )
              .toList(),
          prefetchHooksCallback: ({pendingAttachmentsRefs = false}) {
            return PrefetchHooks(
              db: db,
              explicitlyWatchedTables: [
                if (pendingAttachmentsRefs) db.pendingAttachments,
              ],
              addJoins: null,
              getPrefetchedDataCallback: (items) async {
                return [
                  if (pendingAttachmentsRefs)
                    await $_getPrefetchedDataByColumns<
                      PendingCommandRow,
                      $PendingCommandsTable,
                      PendingAttachmentRow,
                      $PendingAttachmentsTable
                    >(
                      currentTable: table,
                      referencedTable: $$PendingCommandsTableReferences
                          ._pendingAttachmentsRefsTable(db),
                      managerFromTypedResult: (p0) =>
                          $$PendingCommandsTableReferences(
                            db,
                            table,
                            p0,
                          ).pendingAttachmentsRefs,
                      currentColumn: 'client_command_id',
                      referencedColumn: 'client_command_id',
                      typedResults: items,
                    ),
                ];
              },
            );
          },
        ),
      );
}

typedef $$PendingCommandsTableProcessedTableManager =
    ProcessedTableManager<
      _$AppDatabase,
      $PendingCommandsTable,
      PendingCommandRow,
      $$PendingCommandsTableFilterComposer,
      $$PendingCommandsTableOrderingComposer,
      $$PendingCommandsTableAnnotationComposer,
      $$PendingCommandsTableCreateCompanionBuilder,
      $$PendingCommandsTableUpdateCompanionBuilder,
      (PendingCommandRow, $$PendingCommandsTableReferences),
      PendingCommandRow,
      PrefetchHooks Function({bool pendingAttachmentsRefs})
    >;
typedef $$PendingAttachmentsTableCreateCompanionBuilder =
    PendingAttachmentsCompanion Function({
      Value<int> id,
      required String clientCommandId,
      required int position,
      required String localPath,
      required String mimeType,
      required String originalFilename,
      required int sizeBytes,
      Value<String> status,
      Value<String?> uploadedFileId,
    });
typedef $$PendingAttachmentsTableUpdateCompanionBuilder =
    PendingAttachmentsCompanion Function({
      Value<int> id,
      Value<String> clientCommandId,
      Value<int> position,
      Value<String> localPath,
      Value<String> mimeType,
      Value<String> originalFilename,
      Value<int> sizeBytes,
      Value<String> status,
      Value<String?> uploadedFileId,
    });

final class $$PendingAttachmentsTableReferences
    extends
        BaseReferences<
          _$AppDatabase,
          $PendingAttachmentsTable,
          PendingAttachmentRow
        > {
  $$PendingAttachmentsTableReferences(
    super.$_db,
    super.$_table,
    super.$_typedResult,
  );

  static $PendingCommandsTable _clientCommandIdTable(_$AppDatabase db) =>
      db.pendingCommands.createAlias(
        'pending_attachments__client_command_id__pending_commands__client_command_id',
      );

  $$PendingCommandsTableProcessedTableManager get clientCommandId {
    final $_column = $_itemColumn<String>('client_command_id')!;

    final manager = $$PendingCommandsTableTableManager(
      $_db,
      $_db.pendingCommands,
    ).filter((f) => f.clientCommandId.sqlEquals($_column));
    final item = $_typedResult.readTableOrNull(_clientCommandIdTable($_db));
    if (item == null) return manager;
    return ProcessedTableManager(
      manager.$state.copyWith(prefetchedData: [item]),
    );
  }
}

class $$PendingAttachmentsTableFilterComposer
    extends Composer<_$AppDatabase, $PendingAttachmentsTable> {
  $$PendingAttachmentsTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<int> get id => $composableBuilder(
    column: $table.id,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<int> get position => $composableBuilder(
    column: $table.position,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get localPath => $composableBuilder(
    column: $table.localPath,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get mimeType => $composableBuilder(
    column: $table.mimeType,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get originalFilename => $composableBuilder(
    column: $table.originalFilename,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<int> get sizeBytes => $composableBuilder(
    column: $table.sizeBytes,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get status => $composableBuilder(
    column: $table.status,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get uploadedFileId => $composableBuilder(
    column: $table.uploadedFileId,
    builder: (column) => ColumnFilters(column),
  );

  $$PendingCommandsTableFilterComposer get clientCommandId {
    final $$PendingCommandsTableFilterComposer composer = $composerBuilder(
      composer: this,
      getCurrentColumn: (t) => t.clientCommandId,
      referencedTable: $db.pendingCommands,
      getReferencedColumn: (t) => t.clientCommandId,
      builder:
          (
            joinBuilder, {
            $addJoinBuilderToRootComposer,
            $removeJoinBuilderFromRootComposer,
          }) => $$PendingCommandsTableFilterComposer(
            $db: $db,
            $table: $db.pendingCommands,
            $addJoinBuilderToRootComposer: $addJoinBuilderToRootComposer,
            joinBuilder: joinBuilder,
            $removeJoinBuilderFromRootComposer:
                $removeJoinBuilderFromRootComposer,
          ),
    );
    return composer;
  }
}

class $$PendingAttachmentsTableOrderingComposer
    extends Composer<_$AppDatabase, $PendingAttachmentsTable> {
  $$PendingAttachmentsTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<int> get id => $composableBuilder(
    column: $table.id,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<int> get position => $composableBuilder(
    column: $table.position,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get localPath => $composableBuilder(
    column: $table.localPath,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get mimeType => $composableBuilder(
    column: $table.mimeType,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get originalFilename => $composableBuilder(
    column: $table.originalFilename,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<int> get sizeBytes => $composableBuilder(
    column: $table.sizeBytes,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get status => $composableBuilder(
    column: $table.status,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get uploadedFileId => $composableBuilder(
    column: $table.uploadedFileId,
    builder: (column) => ColumnOrderings(column),
  );

  $$PendingCommandsTableOrderingComposer get clientCommandId {
    final $$PendingCommandsTableOrderingComposer composer = $composerBuilder(
      composer: this,
      getCurrentColumn: (t) => t.clientCommandId,
      referencedTable: $db.pendingCommands,
      getReferencedColumn: (t) => t.clientCommandId,
      builder:
          (
            joinBuilder, {
            $addJoinBuilderToRootComposer,
            $removeJoinBuilderFromRootComposer,
          }) => $$PendingCommandsTableOrderingComposer(
            $db: $db,
            $table: $db.pendingCommands,
            $addJoinBuilderToRootComposer: $addJoinBuilderToRootComposer,
            joinBuilder: joinBuilder,
            $removeJoinBuilderFromRootComposer:
                $removeJoinBuilderFromRootComposer,
          ),
    );
    return composer;
  }
}

class $$PendingAttachmentsTableAnnotationComposer
    extends Composer<_$AppDatabase, $PendingAttachmentsTable> {
  $$PendingAttachmentsTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<int> get id =>
      $composableBuilder(column: $table.id, builder: (column) => column);

  GeneratedColumn<int> get position =>
      $composableBuilder(column: $table.position, builder: (column) => column);

  GeneratedColumn<String> get localPath =>
      $composableBuilder(column: $table.localPath, builder: (column) => column);

  GeneratedColumn<String> get mimeType =>
      $composableBuilder(column: $table.mimeType, builder: (column) => column);

  GeneratedColumn<String> get originalFilename => $composableBuilder(
    column: $table.originalFilename,
    builder: (column) => column,
  );

  GeneratedColumn<int> get sizeBytes =>
      $composableBuilder(column: $table.sizeBytes, builder: (column) => column);

  GeneratedColumn<String> get status =>
      $composableBuilder(column: $table.status, builder: (column) => column);

  GeneratedColumn<String> get uploadedFileId => $composableBuilder(
    column: $table.uploadedFileId,
    builder: (column) => column,
  );

  $$PendingCommandsTableAnnotationComposer get clientCommandId {
    final $$PendingCommandsTableAnnotationComposer composer = $composerBuilder(
      composer: this,
      getCurrentColumn: (t) => t.clientCommandId,
      referencedTable: $db.pendingCommands,
      getReferencedColumn: (t) => t.clientCommandId,
      builder:
          (
            joinBuilder, {
            $addJoinBuilderToRootComposer,
            $removeJoinBuilderFromRootComposer,
          }) => $$PendingCommandsTableAnnotationComposer(
            $db: $db,
            $table: $db.pendingCommands,
            $addJoinBuilderToRootComposer: $addJoinBuilderToRootComposer,
            joinBuilder: joinBuilder,
            $removeJoinBuilderFromRootComposer:
                $removeJoinBuilderFromRootComposer,
          ),
    );
    return composer;
  }
}

class $$PendingAttachmentsTableTableManager
    extends
        RootTableManager<
          _$AppDatabase,
          $PendingAttachmentsTable,
          PendingAttachmentRow,
          $$PendingAttachmentsTableFilterComposer,
          $$PendingAttachmentsTableOrderingComposer,
          $$PendingAttachmentsTableAnnotationComposer,
          $$PendingAttachmentsTableCreateCompanionBuilder,
          $$PendingAttachmentsTableUpdateCompanionBuilder,
          (PendingAttachmentRow, $$PendingAttachmentsTableReferences),
          PendingAttachmentRow,
          PrefetchHooks Function({bool clientCommandId})
        > {
  $$PendingAttachmentsTableTableManager(
    _$AppDatabase db,
    $PendingAttachmentsTable table,
  ) : super(
        TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$PendingAttachmentsTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$PendingAttachmentsTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$PendingAttachmentsTableAnnotationComposer(
                $db: db,
                $table: table,
              ),
          updateCompanionCallback:
              ({
                Value<int> id = const Value.absent(),
                Value<String> clientCommandId = const Value.absent(),
                Value<int> position = const Value.absent(),
                Value<String> localPath = const Value.absent(),
                Value<String> mimeType = const Value.absent(),
                Value<String> originalFilename = const Value.absent(),
                Value<int> sizeBytes = const Value.absent(),
                Value<String> status = const Value.absent(),
                Value<String?> uploadedFileId = const Value.absent(),
              }) => PendingAttachmentsCompanion(
                id: id,
                clientCommandId: clientCommandId,
                position: position,
                localPath: localPath,
                mimeType: mimeType,
                originalFilename: originalFilename,
                sizeBytes: sizeBytes,
                status: status,
                uploadedFileId: uploadedFileId,
              ),
          createCompanionCallback:
              ({
                Value<int> id = const Value.absent(),
                required String clientCommandId,
                required int position,
                required String localPath,
                required String mimeType,
                required String originalFilename,
                required int sizeBytes,
                Value<String> status = const Value.absent(),
                Value<String?> uploadedFileId = const Value.absent(),
              }) => PendingAttachmentsCompanion.insert(
                id: id,
                clientCommandId: clientCommandId,
                position: position,
                localPath: localPath,
                mimeType: mimeType,
                originalFilename: originalFilename,
                sizeBytes: sizeBytes,
                status: status,
                uploadedFileId: uploadedFileId,
              ),
          withReferenceMapper: (p0) => p0
              .map(
                (e) => (
                  e.readTable<$PendingAttachmentsTable, PendingAttachmentRow>(
                    table,
                  ),
                  $$PendingAttachmentsTableReferences(db, table, e),
                ),
              )
              .toList(),
          prefetchHooksCallback: ({clientCommandId = false}) {
            return PrefetchHooks(
              db: db,
              explicitlyWatchedTables: [],
              addJoins:
                  <
                    T extends TableManagerState<
                      dynamic,
                      dynamic,
                      dynamic,
                      dynamic,
                      dynamic,
                      dynamic,
                      dynamic,
                      dynamic,
                      dynamic,
                      dynamic,
                      dynamic
                    >
                  >(state) {
                    if (clientCommandId) {
                      state = state.withJoin(
                        currentTable: table,
                        currentColumn: table.clientCommandId,
                        referencedTable: $$PendingAttachmentsTableReferences
                            ._clientCommandIdTable(db),
                        referencedColumn: $$PendingAttachmentsTableReferences
                            ._clientCommandIdTable(db)
                            .clientCommandId,
                      ) as T;
                    }

                    return state;
                  },
              getPrefetchedDataCallback: (items) async {
                return [];
              },
            );
          },
        ),
      );
}

typedef $$PendingAttachmentsTableProcessedTableManager =
    ProcessedTableManager<
      _$AppDatabase,
      $PendingAttachmentsTable,
      PendingAttachmentRow,
      $$PendingAttachmentsTableFilterComposer,
      $$PendingAttachmentsTableOrderingComposer,
      $$PendingAttachmentsTableAnnotationComposer,
      $$PendingAttachmentsTableCreateCompanionBuilder,
      $$PendingAttachmentsTableUpdateCompanionBuilder,
      (PendingAttachmentRow, $$PendingAttachmentsTableReferences),
      PendingAttachmentRow,
      PrefetchHooks Function({bool clientCommandId})
    >;

class $AppDatabaseManager {
  final _$AppDatabase _db;
  $AppDatabaseManager(this._db);
  $$SessionTableTableTableManager get sessionTable =>
      $$SessionTableTableTableManager(_db, _db.sessionTable);
  $$CachedJobsTableTableManager get cachedJobs =>
      $$CachedJobsTableTableManager(_db, _db.cachedJobs);
  $$PendingCommandsTableTableManager get pendingCommands =>
      $$PendingCommandsTableTableManager(_db, _db.pendingCommands);
  $$PendingAttachmentsTableTableManager get pendingAttachments =>
      $$PendingAttachmentsTableTableManager(_db, _db.pendingAttachments);
}
