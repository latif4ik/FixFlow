import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/providers.dart';
import '../../core/theme/app_theme.dart';
import '../../core/util/formatters.dart';
import '../../core/widgets/chips.dart';
import '../../core/widgets/section_card.dart';
import '../jobs/job_models.dart';
import 'outbox_models.dart';
import 'outbox_providers.dart';
import 'outbox_repository.dart';
import 'sync_engine.dart';

String queuedTime(DateTime t, String tz) =>
    DateFormat('HH:mm').format(inZone(t, tz));

/// Asks before throwing away a queued note. Returns true when confirmed.
Future<bool> confirmDiscard(BuildContext context, OutboxItem item) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(item.isConflict ? 'Discard draft?' : 'Discard this note?'),
      content: Text(
        item.photos.isEmpty
            ? 'The note will be deleted from this device and will never be sent. This cannot be undone.'
            : 'The note and its ${item.photos.length} photo(s) will be deleted from this device and will never be sent. This cannot be undone.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('Keep'),
        ),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: AppColors.danger),
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('Discard'),
        ),
      ],
    ),
  );
  return ok ?? false;
}

/// One queued note: "Pending sync - queued 10:42", attempts/last error and the
/// retry / copy / discard choices. Conflicts are never deleted automatically.
class OutboxItemCard extends ConsumerWidget {
  const OutboxItemCard({
    super.key,
    required this.item,
    required this.timezone,
    this.showJob = false,
  });
  final OutboxItem item;
  final String timezone;
  final bool showJob;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final time = queuedTime(item.createdAt, timezone);
    final (icon, label, bg, fg) = switch (item.status) {
      OutboxStatus.conflict => (
        Icons.report_problem_outlined,
        'Conflict · queued $time',
        AppColors.dangerTint,
        AppColors.danger,
      ),
      OutboxStatus.failed => (
        Icons.error_outline,
        'Failed · queued $time',
        AppColors.dangerTint,
        AppColors.danger,
      ),
      OutboxStatus.syncing => (
        Icons.sync,
        'Syncing… · queued $time',
        AppColors.primaryTint,
        AppColors.primaryDark,
      ),
      OutboxStatus.pending => (
        Icons.cloud_upload_outlined,
        'Pending sync · queued $time',
        AppColors.warningTint,
        AppColors.warningText,
      ),
    };
    final busy = item.status == OutboxStatus.syncing;
    return Container(
      key: ValueKey('outbox-${item.commandId}'),
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border.all(
          color: item.isConflict ? AppColors.danger : AppColors.border,
        ),
        borderRadius: BorderRadius.circular(AppRadius.md),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              InfoChip(
                icon: icon,
                label: label,
                background: bg,
                foreground: fg,
              ),
              if (showJob && item.requestLabel.isNotEmpty)
                Text(
                  item.requestLabel,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              if (item.visibility == 'INTERNAL')
                const Text(
                  'Internal note',
                  style: TextStyle(fontSize: 12, color: AppColors.muted),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Text(item.body),
          if (item.photos.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final ph in item.photos)
                  ClipRRect(
                    borderRadius: BorderRadius.circular(AppRadius.sm),
                    child: Image.file(
                      File(ph.localPath),
                      width: 56,
                      height: 56,
                      fit: BoxFit.cover,
                      cacheWidth: 112,
                      errorBuilder: (_, _, _) => Container(
                        width: 56,
                        height: 56,
                        color: AppColors.canvas,
                        child: const Icon(Icons.image_not_supported_outlined),
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              '${item.photos.length} photo${item.photos.length == 1 ? '' : 's'}',
              style: const TextStyle(fontSize: 12, color: AppColors.muted),
            ),
          ],
          if (item.isConflict) ...[
            const SizedBox(height: 8),
            Text(
              item.lastError ?? 'This note could not be sent.',
              style: const TextStyle(color: AppColors.danger),
            ),
            const SizedBox(height: 4),
            const Text(
              'Your draft is kept on this device until you decide.',
              style: TextStyle(fontSize: 12, color: AppColors.muted),
            ),
          ] else if (item.lastError != null || item.attempts > 0) ...[
            const SizedBox(height: 6),
            Text(
              [
                if (item.attempts > 0)
                  'Attempt${item.attempts == 1 ? '' : 's'}: ${item.attempts}',
                ?item.lastError,
              ].join(' · '),
              style: const TextStyle(fontSize: 12, color: AppColors.muted),
            ),
          ],
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              if (item.isConflict)
                OutlinedButton.icon(
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: item.body));
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Note text copied')),
                      );
                    }
                  },
                  icon: const Icon(Icons.copy, size: 18),
                  label: const Text('Copy text'),
                ),
              if (item.retryMeaningful)
                OutlinedButton.icon(
                  onPressed: busy ? null : () => _retry(context, ref),
                  icon: const Icon(Icons.refresh, size: 18),
                  label: Text(item.isConflict ? 'Retry' : 'Retry now'),
                ),
              TextButton.icon(
                style: TextButton.styleFrom(foregroundColor: AppColors.danger),
                onPressed: busy ? null : () => _discard(context, ref),
                icon: const Icon(Icons.delete_outline, size: 18),
                label: Text(item.isConflict ? 'Discard draft' : 'Discard'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _retry(BuildContext context, WidgetRef ref) async {
    await ref.read(outboxRepositoryProvider).retry(item.commandId);
    final report = await ref.read(syncControllerProvider.notifier).syncNow();
    if (context.mounted && report.outcome == SyncOutcome.skipped) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            "You're offline. The note will be sent when you reconnect.",
          ),
        ),
      );
    }
  }

  Future<void> _discard(BuildContext context, WidgetRef ref) async {
    if (!await confirmDiscard(context, item)) return;
    await ref.read(outboxRepositoryProvider).delete(item.commandId);
  }
}

/// Bottom sheet to write a note (+ photos). Works offline and online: it only
/// enqueues; the sync engine delivers it.
Future<bool> showNoteComposer(
  BuildContext context, {
  required String requestId,
}) async {
  final saved = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => NoteComposer(requestId: requestId),
  );
  return saved ?? false;
}

class NoteComposer extends ConsumerStatefulWidget {
  const NoteComposer({super.key, required this.requestId});
  final String requestId;

  @override
  ConsumerState<NoteComposer> createState() => _NoteComposerState();
}

class _NoteComposerState extends ConsumerState<NoteComposer> {
  final _text = TextEditingController();
  final _images = <PickedImage>[];
  String _visibility = 'PUBLIC';
  String? _error;
  bool _saving = false;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _pick(Future<List<PickedImage>> Function() source) async {
    try {
      final picked = await source();
      if (!mounted) return;
      setState(() {
        _images.addAll(picked);
        if (_images.length > OutboxRepository.maxPhotos) {
          _images.removeRange(OutboxRepository.maxPhotos, _images.length);
          _error = 'You can attach up to ${OutboxRepository.maxPhotos} photos.';
        } else {
          _error = null;
        }
      });
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Could not open the camera or gallery.');
      }
    }
  }

  Future<void> _save() async {
    final org = ref.read(selectedOrgIdProvider);
    final user = ref.read(currentUserIdProvider);
    if (org == null || user == null) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await ref
          .read(outboxRepositoryProvider)
          .enqueueNote(
            orgId: org,
            userId: user,
            requestId: widget.requestId,
            body: _text.text,
            visibility: _visibility,
            images: List.of(_images),
          );
    } on OutboxRejected catch (e) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = e.message;
        });
      }
      return;
    }
    // Same path online and offline: the engine sends it right away if it can.
    unawaited(ref.read(syncControllerProvider.notifier).syncNow());
    if (mounted) Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    final offline = ref.watch(isOfflineProvider);
    final picker = ref.watch(photoPickerProvider);
    return Padding(
      padding: EdgeInsets.fromLTRB(
        16,
        0,
        16,
        16 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('New note', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
              offline
                  ? "You're offline. The note is saved on this device and sent when you reconnect."
                  : 'The note is saved on this device first, then sent right away.',
              style: const TextStyle(fontSize: 12, color: AppColors.muted),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _text,
              minLines: 3,
              maxLines: 6,
              maxLength: OutboxRepository.maxBodyLength,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Work note',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 8),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(
                  value: 'PUBLIC',
                  label: Text('Visible to requester'),
                  icon: Icon(Icons.public, size: 18),
                ),
                ButtonSegment(
                  value: 'INTERNAL',
                  label: Text('Internal'),
                  icon: Icon(Icons.lock_outline, size: 18),
                ),
              ],
              selected: {_visibility},
              onSelectionChanged: (s) => setState(() => _visibility = s.first),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (var i = 0; i < _images.length; i++)
                  Chip(
                    avatar: const Icon(Icons.image_outlined, size: 18),
                    label: Text(
                      _images[i].name ?? 'Photo ${i + 1}',
                      overflow: TextOverflow.ellipsis,
                    ),
                    onDeleted: () => setState(() => _images.removeAt(i)),
                  ),
              ],
            ),
            Row(
              children: [
                TextButton.icon(
                  onPressed: _images.length >= OutboxRepository.maxPhotos
                      ? null
                      : () => _pick(picker.fromCamera),
                  icon: const Icon(Icons.photo_camera_outlined),
                  label: const Text('Camera'),
                ),
                TextButton.icon(
                  onPressed: _images.length >= OutboxRepository.maxPhotos
                      ? null
                      : () => _pick(picker.fromGallery),
                  icon: const Icon(Icons.photo_library_outlined),
                  label: const Text('Gallery'),
                ),
              ],
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  _error!,
                  style: const TextStyle(color: AppColors.danger),
                ),
              ),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _saving ? null : _save,
                child: Text(
                  offline ? 'Save note (queue offline)' : 'Save note',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Notes of a job: queued (pending/conflict) notes first, then server notes,
/// plus the "New note" composer entry point.
class JobNotesSection extends ConsumerWidget {
  const JobNotesSection({
    super.key,
    required this.requestId,
    required this.notes,
    required this.timezone,
    required this.canAddNote,
  });
  final String requestId;
  final List<JobNote> notes;
  final String timezone;
  final bool canAddNote;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final queued = ref.watch(outboxForRequestProvider(requestId));
    return SectionCard(
      title: 'Notes',
      trailing: canAddNote
          ? FilledButton.tonalIcon(
              style: FilledButton.styleFrom(minimumSize: const Size(0, 40)),
              onPressed: () => showNoteComposer(context, requestId: requestId),
              icon: const Icon(Icons.edit_note, size: 18),
              label: const Text('New note'),
            )
          : null,
      children: [
        for (final q in queued.reversed)
          OutboxItemCard(item: q, timezone: timezone),
        if (notes.isEmpty && queued.isEmpty) const Text('No notes yet.'),
        for (final n in notes)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${n.authorName ?? 'Unknown'} · ${humanizeEnum(n.kind)} · '
                  '${formatDateTime(n.createdAt, timezone)}'
                  '${n.attachmentCount > 0 ? ' · ${n.attachmentCount} photo${n.attachmentCount == 1 ? '' : 's'}' : ''}',
                  style: const TextStyle(fontSize: 12, color: AppColors.muted),
                ),
                Text(n.body),
              ],
            ),
          ),
      ],
    );
  }
}
