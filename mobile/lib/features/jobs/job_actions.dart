import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_exception.dart';
import '../../core/theme/app_theme.dart';
import '../../core/util/formatters.dart';
import '../../core/widgets/requires_connection.dart';
import '../../core/widgets/section_card.dart';
import '../outbox/outbox_widgets.dart';
import 'complete_job_screen.dart';
import 'job_models.dart';
import 'jobs_providers.dart';

const _actionLabels = <String, (IconData, String)>{
  'accept': (Icons.thumb_up_alt_outlined, 'Accept job'),
  'decline': (Icons.thumb_down_alt_outlined, 'Decline job'),
  'start': (Icons.play_arrow, 'Start work'),
  'resume': (Icons.play_circle_outline, 'Resume work'),
  'block': (Icons.pause_circle_outline, 'Report a blocker'),
  'complete': (Icons.check_circle_outline, 'Mark complete'),
  'add_note': (Icons.note_add_outlined, 'Add note'),
  'add_photo': (Icons.photo_camera_outlined, 'Add photo'),
  'log_materials': (Icons.inventory_2_outlined, 'Log materials'),
  'submit_estimate': (Icons.request_quote_outlined, 'Submit estimate'),
};

String actionLabel(String action) =>
    _actionLabels[action]?.$2 ?? humanizeEnum(action);

/// Order in which controls are shown (primary first, destructive last).
const _order = [
  'accept',
  'start',
  'resume',
  'complete',
  'block',
  'decline',
  'add_note',
];

/// Minimum length of a decline / blocker reason and of a resume note.
const minReasonLength = 5;

/// Turns any failure of an online-only action into a message for the user
/// (MOB-03: never imply success, say what happened and what to do).
String actionErrorMessage(Object e) {
  if (e is NetworkException) {
    return e.timedOut
        ? 'The server took too long to respond. The action may not have been '
              'applied - check the job and try again.'
        : 'Cannot reach the server. Nothing was changed; try again when you '
              'are online.';
  }
  if (e is ApiException) {
    if (e.isUnauthorized) return 'Your session expired. Please sign in again.';
    if (e.isForbidden || e.isNotFound) {
      return 'You are no longer assigned to this job or cannot do this '
          'anymore. (${e.message})';
    }
    final details = e.details;
    final extra = <String>[];
    if (details is List) {
      for (final d in details) {
        if (d is Map && d['message'] != null) extra.add('${d['message']}');
      }
    }
    return extra.isEmpty ? e.message : '${e.message} ${extra.join(' ')}';
  }
  return 'Something went wrong. Please try again.';
}

Future<void> showActionError(BuildContext context, String title, Object e) =>
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: const Icon(Icons.error_outline, color: AppColors.danger),
        title: Text(title),
        content: Text(actionErrorMessage(e)),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('OK'),
          ),
        ],
      ),
    );

/// Dialog asking for a required free-text reason/note.
Future<String?> askForText(
  BuildContext context, {
  required String title,
  required String label,
  required String confirmLabel,
  int minLength = minReasonLength,
  String? helper,
}) => showDialog<String>(
  context: context,
  builder: (_) => _TextPromptDialog(
    title: title,
    label: label,
    confirmLabel: confirmLabel,
    minLength: minLength,
    helper: helper,
  ),
);

class _TextPromptDialog extends StatefulWidget {
  const _TextPromptDialog({
    required this.title,
    required this.label,
    required this.confirmLabel,
    required this.minLength,
    this.helper,
  });
  final String title;
  final String label;
  final String confirmLabel;
  final int minLength;
  final String? helper;

  @override
  State<_TextPromptDialog> createState() => _TextPromptDialogState();
}

class _TextPromptDialogState extends State<_TextPromptDialog> {
  final _c = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  void _submit() {
    final v = _c.text.trim();
    if (v.length < widget.minLength) {
      setState(
        () => _error =
            '${widget.label} is required (at least ${widget.minLength} characters).',
      );
      return;
    }
    Navigator.pop(context, v);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.title),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (widget.helper != null) ...[
          Text(widget.helper!),
          const SizedBox(height: 8),
        ],
        TextField(
          controller: _c,
          autofocus: true,
          minLines: 2,
          maxLines: 4,
          maxLength: 2000,
          textCapitalization: TextCapitalization.sentences,
          decoration: InputDecoration(
            labelText: widget.label,
            errorText: _error,
            border: const OutlineInputBorder(),
          ),
          onChanged: (_) {
            if (_error != null) setState(() => _error = null);
          },
        ),
      ],
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(onPressed: _submit, child: Text(widget.confirmLabel)),
    ],
  );
}

/// Interactive actions of a job (MOB-01/02, LIFE-02..05), driven by the
/// server's `allowed_actions`. Everything except notes needs a connection
/// (MOB-08) and is never applied locally: the UI changes only after the
/// server answered 2xx (MOB-03).
class JobActionsSection extends ConsumerStatefulWidget {
  const JobActionsSection({
    super.key,
    required this.job,
    required this.actions,
    this.startBlockedReason,
  });
  final JobDetail job;
  final List<String> actions;

  /// `start_blocked_reason` from the inbox item (estimate not approved yet).
  final String? startBlockedReason;

  /// Actions that work offline (queued in the outbox); everything else needs
  /// a connection (MOB-08) and is shown as unavailable while offline.
  static const offlineCapable = {'add_note', 'add_photo'};

  @override
  ConsumerState<JobActionsSection> createState() => _JobActionsSectionState();
}

class _JobActionsSectionState extends ConsumerState<JobActionsSection> {
  /// Action in flight; blocks every other control (double-tap protection).
  String? _busy;

  String get _id => widget.job.id;

  /// Reason why Start is unavailable, or null.
  String? get _startBlocked {
    if (widget.actions.contains('start')) return null;
    final r = widget.startBlockedReason;
    if (r != null && r.isNotEmpty) return r;
    final e = widget.job.estimate;
    if (widget.job.status == 'ACCEPTED' &&
        e != null &&
        e.status != 'APPROVED') {
      return 'Waiting for the estimate to be approved '
          '(${humanizeEnum(e.status)}).';
    }
    return null;
  }

  Future<void> _run(
    String action,
    Future<void> Function() call, {
    required String success,
    bool leaveAfter = false,
  }) async {
    if (_busy != null) return;
    final messenger = ScaffoldMessenger.of(context);
    final router = GoRouter.of(context);
    final dialogContext = context;
    setState(() => _busy = action);
    try {
      await call();
    } catch (e) {
      if (mounted) setState(() => _busy = null);
      // The job may have changed under us: refresh what the user sees.
      if (e is ApiException && !e.isUnauthorized) refreshJobData(ref, _id);
      if (dialogContext.mounted) {
        await showActionError(dialogContext, 'Could not ${_verb(action)}', e);
      }
      return;
    }
    refreshJobData(ref, _id, includeDetail: !leaveAfter);
    messenger.showSnackBar(SnackBar(content: Text(success)));
    if (mounted) setState(() => _busy = null);
    if (leaveAfter) router.go('/inbox');
  }

  String _verb(String action) => switch (action) {
    'accept' => 'accept the job',
    'decline' => 'decline the job',
    'start' => 'start work',
    'block' => 'report the blocker',
    'resume' => 'resume work',
    _ => 'complete the action',
  };

  Future<void> _accept() => _run(
    'accept',
    () => ref.read(jobActionsRepositoryProvider).accept(_id),
    success: 'Job accepted.',
  );

  Future<void> _start() => _run(
    'start',
    () => ref.read(jobActionsRepositoryProvider).start(_id),
    success: 'Work started.',
  );

  Future<void> _decline() async {
    final reason = await askForText(
      context,
      title: 'Decline this job?',
      label: 'Reason',
      confirmLabel: 'Decline job',
      helper:
          'The job goes back to the dispatcher and disappears from your inbox.',
    );
    if (reason == null || !mounted) return;
    await _run(
      'decline',
      () => ref.read(jobActionsRepositoryProvider).decline(_id, reason),
      success: 'Job declined.',
      leaveAfter: true,
    );
  }

  Future<void> _block() async {
    final reason = await askForText(
      context,
      title: 'Report a blocker',
      label: 'Reason',
      confirmLabel: 'Report blocker',
      helper: 'What is stopping you from finishing the job?',
    );
    if (reason == null || !mounted) return;
    await _run(
      'block',
      () => ref.read(jobActionsRepositoryProvider).block(_id, reason),
      success: 'Blocker reported.',
    );
  }

  Future<void> _resume() async {
    final note = await askForText(
      context,
      title: 'Resume work',
      label: 'Resolution note',
      confirmLabel: 'Resume work',
      helper: 'How was the blocker resolved?',
    );
    if (note == null || !mounted) return;
    await _run(
      'resume',
      () => ref.read(jobActionsRepositoryProvider).resume(_id, note),
      success: 'Work resumed.',
    );
  }

  Future<void> _complete() async {
    if (_busy != null) return;
    final done = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            CompleteJobScreen(requestId: _id, displayId: widget.job.displayId),
      ),
    );
    if (done == true && mounted) {
      refreshJobData(ref, _id);
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Job completed.')));
    }
  }

  VoidCallback? _handler(String a) => switch (a) {
    'accept' => _accept,
    'start' => _start,
    'resume' => _resume,
    'complete' => _complete,
    'block' => _block,
    'decline' => _decline,
    _ => null,
  };

  @override
  Widget build(BuildContext context) {
    final known = [
      for (final a in _order)
        if (widget.actions.contains(a)) a,
    ];
    final unknown = [
      for (final a in widget.actions)
        if (!_order.contains(a)) a,
    ];
    final blocked = _startBlocked;
    return SectionCard(
      title: 'Available actions',
      children: [
        if (widget.actions.isEmpty && blocked == null)
          const Text('No actions are available for this job right now.'),
        if (blocked != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                FilledButton.icon(
                  onPressed: null,
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Start work'),
                ),
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    'Cannot start yet: $blocked',
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppColors.warningText,
                    ),
                  ),
                ),
              ],
            ),
          ),
        for (final a in known) _control(context, a),
        for (final a in unknown)
          // Server-driven action this version has no control for: list it
          // read-only instead of hiding it.
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              children: [
                Icon(_actionLabels[a]?.$1 ?? Icons.bolt, size: 18),
                const SizedBox(width: 8),
                Expanded(child: Text(actionLabel(a))),
              ],
            ),
          ),
        if (_busy != null)
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: LinearProgressIndicator(),
          ),
      ],
    );
  }

  Widget _control(BuildContext context, String a) {
    final (icon, label) = _actionLabels[a]!;
    if (a == 'add_note') {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: OutlinedButton.icon(
          onPressed: () => showNoteComposer(context, requestId: _id),
          icon: Icon(icon),
          label: Text(label),
        ),
      );
    }
    final primary = a == 'accept' || a == 'start' || a == 'complete';
    final destructive = a == 'decline';
    final busy = _busy == a;
    Widget button(bool enabled) {
      final onPressed = enabled && _busy == null ? _handler(a) : null;
      final child = Text(busy ? '$label…' : label);
      final iconW = busy
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : Icon(icon);
      if (primary) {
        return FilledButton.icon(
          onPressed: onPressed,
          icon: iconW,
          label: child,
        );
      }
      return OutlinedButton.icon(
        onPressed: onPressed,
        style: destructive
            ? OutlinedButton.styleFrom(foregroundColor: AppColors.danger)
            : null,
        icon: iconW,
        label: child,
      );
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: RequiresConnection(builder: (context, enabled) => button(enabled)),
    );
  }
}
