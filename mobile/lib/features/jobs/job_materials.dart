import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../../core/api/api_exception.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/requires_connection.dart';
import '../../core/widgets/section_card.dart';
import '../../core/widgets/state_views.dart';
import 'job_actions.dart' show actionErrorMessage;
import 'job_actions_repository.dart';
import 'job_models.dart';
import 'jobs_providers.dart';

/// INV-03: positive quantity with at most three decimals ("2", "0.5", "1.250").
final _quantityPattern = RegExp(r'^\d{1,9}([.,]\d{1,3})?$');

/// Returns an error message for an invalid quantity, or null when valid.
String? validateQuantity(String raw) {
  final v = raw.trim();
  if (v.isEmpty) return 'Enter a quantity.';
  if (!_quantityPattern.hasMatch(v)) {
    return 'Use a number with up to 3 decimals, e.g. 2 or 0.5.';
  }
  final n = double.tryParse(v.replaceAll(',', '.'));
  if (n == null || n <= 0) return 'Quantity must be greater than 0.';
  return null;
}

/// Materials recorded on the job plus the "Record material" entry point
/// (assigned technician, IN_PROGRESS only, online-only).
class JobMaterialsSection extends ConsumerWidget {
  const JobMaterialsSection({super.key, required this.job});
  final JobDetail job;

  bool get canRecord =>
      job.status == 'IN_PROGRESS' && job.allowedActions.contains('complete');

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!canRecord && job.materials.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: SectionCard(
        title: 'Materials used',
        children: [
          if (job.materials.isEmpty) const Text('No materials recorded yet.'),
          for (final m in job.materials)
            KeyValueRow(
              m.name,
              '${m.quantity}${m.unit.isEmpty ? '' : ' ${m.unit}'}',
            ),
          if (canRecord) ...[
            const SizedBox(height: 8),
            RequiresConnection(
              builder: (context, enabled) => FilledButton.tonalIcon(
                onPressed: enabled ? () => _open(context, ref) : null,
                icon: const Icon(Icons.inventory_2_outlined),
                label: const Text('Record material'),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _open(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    final res = await showModalBottomSheet<MaterialRecord>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => RecordMaterialSheet(requestId: job.id),
    );
    if (res != null) {
      refreshJobData(ref, job.id);
      ref.invalidate(inventoryProvider);
      messenger.showSnackBar(
        SnackBar(
          content: Text('Recorded ${res.quantity} ${res.unit} of ${res.name}.'),
        ),
      );
    }
  }
}

class RecordMaterialSheet extends ConsumerStatefulWidget {
  const RecordMaterialSheet({super.key, required this.requestId});
  final String requestId;

  @override
  ConsumerState<RecordMaterialSheet> createState() =>
      _RecordMaterialSheetState();
}

class _RecordMaterialSheetState extends ConsumerState<RecordMaterialSheet> {
  final _search = TextEditingController();
  final _qty = TextEditingController();

  /// Idempotency key: generated when the sheet opens and reused for retries
  /// of the SAME attempt, so a timeout + retry can never consume twice.
  String _commandId = const Uuid().v4();
  InventoryItem? _item;
  String? _qtyError;
  String? _formError;
  bool _submitting = false;

  /// A request was sent but its outcome is unknown (timeout/connection drop).
  /// The inputs are locked so the retry carries the identical payload.
  bool _unknownOutcome = false;

  @override
  void dispose() {
    _search.dispose();
    _qty.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitting) return;
    final item = _item;
    final err = validateQuantity(_qty.text);
    setState(() {
      _qtyError = err;
      _formError = item == null ? 'Choose a material first.' : null;
    });
    if (err != null || item == null) return;
    setState(() {
      _submitting = true;
      _formError = null;
    });
    try {
      final rec = await ref
          .read(jobActionsRepositoryProvider)
          .consumeMaterial(
            widget.requestId,
            commandId: _commandId,
            itemId: item.id,
            quantity: _qty.text.trim().replaceAll(',', '.'),
          );
      if (mounted) Navigator.pop(context, rec);
    } on NetworkException catch (_) {
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _unknownOutcome = true;
        _formError =
            'The connection dropped before we got an answer. Nothing is '
            'shown as recorded. Tap "Retry" to confirm - the server records '
            'this usage only once.';
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      var msg = e.message;
      if (e.code == 'insufficient_stock') {
        final d = e.details;
        final avail = d is Map ? d['available'] : null;
        msg = avail == null
            ? 'Not enough stock for ${item.name}.'
            : 'Not enough stock for ${item.name}. Available: $avail ${item.unit}.';
      } else if (e.isForbidden || e.isNotFound || e.isConflict) {
        msg = actionErrorMessage(e);
      }
      setState(() {
        _submitting = false;
        // Definitive rejection: nothing was stored, a new attempt gets a new key.
        _commandId = const Uuid().v4();
        _formError = msg;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final inv = ref.watch(inventoryProvider);
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
            Text(
              'Record material',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 4),
            const Text(
              'Stock is deducted right away on the server.',
              style: TextStyle(fontSize: 12, color: AppColors.muted),
            ),
            const SizedBox(height: 12),
            if (_item != null)
              Card(
                child: ListTile(
                  dense: true,
                  leading: const Icon(
                    Icons.check_circle,
                    color: AppColors.primary,
                  ),
                  title: Text('${_item!.code} · ${_item!.name}'),
                  subtitle: Text('In stock: ${_item!.stock} ${_item!.unit}'),
                  trailing: _unknownOutcome || _submitting
                      ? null
                      : TextButton(
                          onPressed: () => setState(() => _item = null),
                          child: const Text('Change'),
                        ),
                ),
              )
            else ...[
              TextField(
                controller: _search,
                onChanged: (_) => setState(() {}),
                decoration: const InputDecoration(
                  labelText: 'Search materials (code or name)',
                  prefixIcon: Icon(Icons.search),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                height: 220,
                child: inv.when(
                  loading: () => const LoadingView(label: 'Loading materials…'),
                  error: (e, _) => ProblemView(
                    error: e,
                    onRetry: () => ref.invalidate(inventoryProvider),
                  ),
                  data: (items) {
                    final q = _search.text.trim().toLowerCase();
                    final shown = [
                      for (final i in items)
                        if (q.isEmpty ||
                            i.code.toLowerCase().contains(q) ||
                            i.name.toLowerCase().contains(q))
                          i,
                    ];
                    if (shown.isEmpty) {
                      return const Center(
                        child: Text('No matching materials.'),
                      );
                    }
                    return ListView.builder(
                      itemCount: shown.length,
                      itemBuilder: (context, i) {
                        final it = shown[i];
                        return ListTile(
                          dense: true,
                          title: Text('${it.code} · ${it.name}'),
                          subtitle: Text('In stock: ${it.stock} ${it.unit}'),
                          onTap: () => setState(() => _item = it),
                        );
                      },
                    );
                  },
                ),
              ),
            ],
            const SizedBox(height: 8),
            TextField(
              controller: _qty,
              enabled: !_unknownOutcome && !_submitting,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              onChanged: (_) {
                if (_qtyError != null) setState(() => _qtyError = null);
              },
              decoration: InputDecoration(
                labelText: _item == null
                    ? 'Quantity'
                    : 'Quantity (${_item!.unit})',
                errorText: _qtyError,
                border: const OutlineInputBorder(),
              ),
            ),
            if (_formError != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  _formError!,
                  style: const TextStyle(color: AppColors.danger),
                ),
              ),
            const SizedBox(height: 12),
            RequiresConnection(
              builder: (context, enabled) => SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: enabled && !_submitting ? _submit : null,
                  child: Text(
                    _submitting
                        ? 'Recording…'
                        : _unknownOutcome
                        ? 'Retry'
                        : 'Record material',
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
