import 'package:flutter/material.dart';

import '../api/api_exception.dart';
import '../theme/app_theme.dart';

/// Visual kinds for MOB-03 states.
enum ViewProblem {
  error,
  offline,
  permissionDenied,
  notFound,
  sessionExpired,
  conflict,
}

class ProblemInfo {
  const ProblemInfo(this.kind, this.icon, this.title, this.message);
  final ViewProblem kind;
  final IconData icon;
  final String title;
  final String message;
}

/// Maps any thrown object to a user-facing state. [notFoundMessage] lets a
/// screen say what a 404 means for it.
ProblemInfo describeProblem(
  Object error, {
  String notFoundMessage = 'This item no longer exists.',
}) {
  if (error is NetworkException) {
    return ProblemInfo(
      ViewProblem.offline,
      Icons.cloud_off,
      "You're offline",
      error.timedOut
          ? 'The server took too long to respond. Check your connection and the server address.'
          : 'Cannot reach the server. Check your connection and the server address.',
    );
  }
  if (error is ApiException) {
    if (error.isUnauthorized) {
      return const ProblemInfo(
        ViewProblem.sessionExpired,
        Icons.lock_clock,
        'Session expired',
        'Please sign in again.',
      );
    }
    if (error.isForbidden) {
      return ProblemInfo(
        ViewProblem.permissionDenied,
        Icons.block,
        'No access',
        error.message.isEmpty
            ? 'You do not have permission to view this.'
            : error.message,
      );
    }
    if (error.isNotFound) {
      return ProblemInfo(
        ViewProblem.notFound,
        Icons.search_off,
        'Not found',
        notFoundMessage,
      );
    }
    if (error.isConflict) {
      return ProblemInfo(
        ViewProblem.conflict,
        Icons.sync_problem,
        'Conflict',
        error.message,
      );
    }
    return ProblemInfo(
      ViewProblem.error,
      Icons.error_outline,
      'Something went wrong',
      error.requestId == null
          ? error.message
          : '${error.message}\nReference: ${error.requestId}',
    );
  }
  return const ProblemInfo(
    ViewProblem.error,
    Icons.error_outline,
    'Something went wrong',
    'An unexpected error occurred.',
  );
}

class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.label = 'Loading…'});
  final String label;

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const CircularProgressIndicator(),
        const SizedBox(height: 12),
        Text(label),
      ],
    ),
  );
}

class _Message extends StatelessWidget {
  const _Message({
    required this.icon,
    required this.title,
    required this.message,
    this.color = AppColors.muted,
    this.actions = const [],
  });
  final IconData icon;
  final String title;
  final String message;
  final Color color;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) => Center(
    child: SingleChildScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 48, color: color),
          const SizedBox(height: 12),
          Text(
            title,
            style: Theme.of(context).textTheme.titleMedium,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 6),
          Text(message, textAlign: TextAlign.center),
          if (actions.isNotEmpty) const SizedBox(height: 16),
          ...actions,
        ],
      ),
    ),
  );
}

class EmptyView extends StatelessWidget {
  const EmptyView({
    super.key,
    required this.title,
    required this.message,
    this.icon = Icons.inbox_outlined,
  });
  final String title;
  final String message;
  final IconData icon;

  @override
  Widget build(BuildContext context) =>
      _Message(icon: icon, title: title, message: message);
}

/// Generic error/offline/permission/not-found view with a retry action.
class ProblemView extends StatelessWidget {
  const ProblemView({
    super.key,
    required this.error,
    this.onRetry,
    this.notFoundMessage = 'This item no longer exists.',
    this.extraActions = const [],
  });
  final Object error;
  final VoidCallback? onRetry;
  final String notFoundMessage;
  final List<Widget> extraActions;

  @override
  Widget build(BuildContext context) {
    final p = describeProblem(error, notFoundMessage: notFoundMessage);
    final color = switch (p.kind) {
      ViewProblem.offline => AppColors.warningText,
      ViewProblem.error ||
      ViewProblem.permissionDenied ||
      ViewProblem.conflict => AppColors.danger,
      _ => AppColors.muted,
    };
    final retryable =
        onRetry != null &&
        p.kind != ViewProblem.notFound &&
        p.kind != ViewProblem.permissionDenied;
    return _Message(
      icon: p.icon,
      title: p.title,
      message: p.message,
      color: color,
      actions: [
        if (retryable)
          FilledButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Try again'),
          ),
        ...extraActions,
      ],
    );
  }
}
