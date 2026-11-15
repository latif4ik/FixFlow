import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';

/// Owns the signed-in session: restore on start, sign in/out, org switching,
/// expiry. State is synchronous so the router can redirect on it.
class SessionController extends Notifier<SessionState> {
  @override
  SessionState build() {
    unawaited(Future<void>.microtask(_restore));
    return const SessionState.bootstrapping();
  }

  Future<void> _restore() async {
    final token = await ref.read(tokenStoreProvider).read();
    final saved = await ref.read(sessionStoreProvider).load();
    if (token == null || saved == null) {
      state = SessionState.signedOut(lastEmail: saved?.user.email);
      return;
    }
    if (saved.expiresAt != null && saved.expiresAt!.isBefore(DateTime.now())) {
      await ref.read(tokenStoreProvider).clear();
      state = SessionState(
        status: SessionStatus.expired,
        lastEmail: saved.user.email,
      );
      return;
    }
    final tech = saved.memberships.where((m) => m.isTechnician).toList();
    state = SessionState(
      status: SessionStatus.signedIn,
      token: token,
      user: saved.user,
      memberships: saved.memberships,
      selectedOrgId: autoSelectOrgId(tech, saved.selectedOrgId),
    );
  }

  /// Throws `AppException` (ApiException 401 = bad credentials).
  Future<void> signIn(String email, String password) async {
    final result = await ref
        .read(authRepositoryProvider)
        .login(email, password);
    final tech = result.memberships.where((m) => m.isTechnician).toList();
    final orgId = autoSelectOrgId(tech, state.selectedOrgId);
    await ref.read(tokenStoreProvider).write(result.token);
    // A different user must never see the previous user's cached jobs
    // (the queued outbox is kept but is only replayed by its owner).
    final previous = await ref.read(sessionStoreProvider).load();
    if (previous != null && previous.user.id != result.user.id) {
      await ref.read(appDatabaseProvider).clearReadCache();
    }
    await ref
        .read(sessionStoreProvider)
        .save(
          user: result.user,
          memberships: result.memberships,
          selectedOrgId: orgId,
          expiresAt: result.expiresAt,
        );
    state = SessionState(
      status: SessionStatus.signedIn,
      token: result.token,
      user: result.user,
      memberships: result.memberships,
      selectedOrgId: orgId,
    );
  }

  Future<void> selectOrg(String orgId) async {
    if (!state.isSignedIn) return;
    final ok = state.technicianMemberships.any(
      (m) => m.organization.id == orgId,
    );
    if (!ok) return;
    await ref.read(sessionStoreProvider).updateSelectedOrg(orgId);
    // Org-scoped providers watch selectedOrgIdProvider and reset themselves.
    state = state.copyWith(selectedOrgId: orgId);
  }

  /// Called by the API layer on 401 for an authenticated request.
  Future<void> markExpired() async {
    if (state.status != SessionStatus.signedIn) return;
    final email = state.user?.email;
    await ref.read(tokenStoreProvider).clear();
    // Keep the persisted user row (for prefill) and ALL queued offline work.
    state = SessionState(status: SessionStatus.expired, lastEmail: email);
  }

  Future<void> signOut() async {
    final email = state.user?.email ?? state.lastEmail;
    if (state.isSignedIn) {
      await ref.read(authRepositoryProvider).logout();
    }
    await ref.read(tokenStoreProvider).clear();
    // Clears session + read cache; keeps pending_commands/attachments.
    await ref.read(appDatabaseProvider).clearReadCache();
    state = SessionState.signedOut(lastEmail: email);
  }
}
