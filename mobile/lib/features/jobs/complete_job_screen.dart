import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:uuid/uuid.dart';

import '../../core/api/api_exception.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/requires_connection.dart';
import '../outbox/outbox_providers.dart';
import '../outbox/outbox_repository.dart';
import 'job_actions.dart';
import 'jobs_providers.dart';

/// LIFE-05: completion needs a note of at least [minNoteLength] characters
/// and at least one valid completion photo.
const minNoteLength = 20;

enum PhotoState { ready, uploading, uploaded, failed }

class _CompletionPhoto {
  _CompletionPhoto(this.path, this.name);
  final String path;
  final String name;

  /// Kept until the upload succeeded, so a retry is replay-safe (the server
  /// answers 200 with the same file instead of storing a duplicate).
  final String commandId = const Uuid().v4();
  PhotoState state = PhotoState.ready;
  String? fileId;
  String? error;
}

/// Full-screen completion form. Pops with `true` only after the server
/// accepted the completion (2xx); never shows success otherwise.
class CompleteJobScreen extends ConsumerStatefulWidget {
  const CompleteJobScreen({
    super.key,
    required this.requestId,
    required this.displayId,
  });
  final String requestId;
  final String displayId;

  @override
  ConsumerState<CompleteJobScreen> createState() => _CompleteJobScreenState();
}

class _CompleteJobScreenState extends ConsumerState<CompleteJobScreen> {
  final _note = TextEditingController();
  final _photos = <_CompletionPhoto>[];
  String? _noteError;
  String? _photoError;
  String? _submitError;
  bool _submitting = false;

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  int get _noteLength => _note.text.trim().length;

  Future<void> _pick(Future<List<PickedImage>> Function() source) async {
    try {
      final picked = await source();
      for (final img in picked) {
        if (_photos.length >= OutboxRepository.maxPhotos) {
          _photoError =
              'You can attach up to ${OutboxRepository.maxPhotos} photos.';
          break;
        }
        final name = img.name ?? p.basename(img.path);
        final err = await _validate(img.path, name);
        if (err != null) {
          _photoError = err;
          continue;
        }
        _photoError = null;
        _photos.add(_CompletionPhoto(img.path, name));
      }
    } catch (_) {
      _photoError = 'Could not open the camera or gallery.';
    }
    if (mounted) setState(() {});
  }

  Future<String?> _validate(String path, String name) async {
    final f = File(path);
    if (!await f.exists()) return 'Photo "$name" could not be read.';
    final size = await f.length();
    if (size == 0) return 'Photo "$name" is empty.';
    if (size > OutboxRepository.maxPhotoBytes) {
      return 'Photo "$name" is larger than 10 MB.';
    }
    final raf = await f.open();
    final head = await raf.read(16);
    await raf.close();
    if (sniffImage(head) == null) {
      return 'Photo "$name" is not a JPEG, PNG or WebP image.';
    }
    return null;
  }

  Future<void> _submit() async {
    if (_submitting) return;
    final note = _note.text.trim();
    setState(() {
      _submitError = null;
      _noteError = note.length < minNoteLength
          ? 'Describe the work done in at least $minNoteLength characters '
                '(${note.length}/$minNoteLength).'
          : null;
      _photoError = _photos.isEmpty
          ? 'Add at least one completion photo.'
          : null;
    });
    if (_noteError != null || _photoError != null) return;

    setState(() => _submitting = true);
    final repo = ref.read(jobActionsRepositoryProvider);
    // 1) upload every photo that is not on the server yet.
    for (var i = 0; i < _photos.length; i++) {
      final ph = _photos[i];
      if (ph.state == PhotoState.uploaded) continue;
      setState(() {
        ph.state = PhotoState.uploading;
        ph.error = null;
      });
      try {
        ph.fileId = await repo.uploadCompletionPhoto(
          widget.requestId,
          path: ph.path,
          commandId: ph.commandId,
          index: 0,
        );
        if (!mounted) return;
        setState(() => ph.state = PhotoState.uploaded);
      } catch (e) {
        if (!mounted) return;
        setState(() {
          ph.state = PhotoState.failed;
          ph.error = actionErrorMessage(e);
          _submitting = false;
          _submitError =
              'Photo ${i + 1} could not be uploaded, so the job was NOT '
              'completed. Photos already uploaded stay attached; tap '
              '"Retry" to continue.';
        });
        return;
      }
    }
    // 2) complete: only the server's 2xx counts as success.
    try {
      await repo.complete(widget.requestId, note);
    } catch (e) {
      if (!mounted) return;
      if (e is ApiException && !e.isUnauthorized) {
        refreshJobData(ref, widget.requestId);
      }
      setState(() {
        _submitting = false;
        _submitError =
            'The job was NOT completed: ${actionErrorMessage(e)} '
            'Your photos are already attached to the job on the server; fix '
            'the problem and tap "Retry".';
      });
      return;
    }
    if (mounted) Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final picker = ref.watch(photoPickerProvider);
    final anyFailed =
        _submitError != null ||
        _photos.any((p) => p.state == PhotoState.failed);
    final canAddMore = _photos.length < OutboxRepository.maxPhotos;
    return Scaffold(
      appBar: AppBar(title: Text('Complete ${widget.displayId}')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text(
            'Write what was done and attach at least one photo of the '
            'finished work. Completion needs a connection.',
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _note,
            enabled: !_submitting,
            minLines: 4,
            maxLines: 8,
            maxLength: 2000,
            textCapitalization: TextCapitalization.sentences,
            onChanged: (_) => setState(() => _noteError = null),
            decoration: InputDecoration(
              labelText: 'Completion note',
              errorText: _noteError,
              border: const OutlineInputBorder(),
              counterText: '$_noteLength/$minNoteLength minimum',
              counterStyle: TextStyle(
                color: _noteLength >= minNoteLength
                    ? AppColors.primaryDark
                    : AppColors.muted,
              ),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Completion photos',
            style: Theme.of(context).textTheme.titleSmall,
          ),
          const SizedBox(height: 6),
          for (var i = 0; i < _photos.length; i++) _photoTile(i),
          Row(
            children: [
              TextButton.icon(
                onPressed: _submitting || !canAddMore
                    ? null
                    : () => _pick(picker.fromCamera),
                icon: const Icon(Icons.photo_camera_outlined),
                label: const Text('Camera'),
              ),
              TextButton.icon(
                onPressed: _submitting || !canAddMore
                    ? null
                    : () => _pick(picker.fromGallery),
                icon: const Icon(Icons.photo_library_outlined),
                label: const Text('Gallery'),
              ),
            ],
          ),
          if (_photoError != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(
                _photoError!,
                style: const TextStyle(color: AppColors.danger),
              ),
            ),
          if (_submitError != null)
            Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.dangerTint,
                borderRadius: BorderRadius.circular(AppRadius.sm),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(
                    Icons.error_outline,
                    color: AppColors.danger,
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _submitError!,
                      style: const TextStyle(color: AppColors.danger),
                    ),
                  ),
                ],
              ),
            ),
          RequiresConnection(
            reason: 'Completing a job requires a connection',
            builder: (context, enabled) => SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: enabled && !_submitting ? _submit : null,
                icon: _submitting
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.check_circle_outline),
                label: Text(
                  _submitting
                      ? 'Completing…'
                      : anyFailed
                      ? 'Retry'
                      : 'Complete job',
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _photoTile(int i) {
    final ph = _photos[i];
    final (icon, text, color) = switch (ph.state) {
      PhotoState.ready => (
        Icons.image_outlined,
        'Ready to upload',
        AppColors.muted,
      ),
      PhotoState.uploading => (
        Icons.cloud_upload_outlined,
        'Uploading…',
        AppColors.muted,
      ),
      PhotoState.uploaded => (
        Icons.check_circle,
        'Uploaded',
        AppColors.primaryDark,
      ),
      PhotoState.failed => (
        Icons.error_outline,
        'Upload failed',
        AppColors.danger,
      ),
    };
    return Card(
      margin: const EdgeInsets.only(bottom: 6),
      child: ListTile(
        dense: true,
        leading: ph.state == PhotoState.uploading
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : Icon(icon, color: color),
        title: Text(ph.name, overflow: TextOverflow.ellipsis),
        subtitle: Text(
          ph.error == null ? text : '$text: ${ph.error}',
          style: TextStyle(color: color),
        ),
        trailing: ph.state == PhotoState.uploaded || _submitting
            ? null
            : IconButton(
                tooltip: 'Remove photo',
                icon: const Icon(Icons.close),
                onPressed: () => setState(() => _photos.removeAt(i)),
              ),
      ),
    );
  }
}
