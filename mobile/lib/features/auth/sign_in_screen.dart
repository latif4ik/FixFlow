import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_exception.dart';
import '../../core/config/app_config.dart';
import '../../core/providers.dart';
import '../../core/theme/app_theme.dart';
import 'validators.dart';

class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key});

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  final _formKey = GlobalKey<FormState>();
  final _serverKey = GlobalKey<FormFieldState<String>>();
  late final TextEditingController _email;
  final _password = TextEditingController();
  late final TextEditingController _server;
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _email = TextEditingController(text: ref.read(sessionProvider).lastEmail);
    _server = TextEditingController(text: ref.read(serverUrlProvider));
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _server.dispose();
    super.dispose();
  }

  Future<void> _saveServer() async {
    if (!(_serverKey.currentState?.validate() ?? false)) return;
    await ref.read(serverUrlProvider.notifier).set(_server.text);
    if (!mounted) return;
    _server.text = ref.read(serverUrlProvider);
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text('Server set to ${_server.text}')));
  }

  Future<void> _resetServer() async {
    await ref.read(serverUrlProvider.notifier).reset();
    if (!mounted) return;
    setState(() => _server.text = ref.read(serverUrlProvider));
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(sessionProvider.notifier)
          .signIn(_email.text, _password.text);
      // Router redirects on session change.
    } on NetworkException {
      _error =
          'Cannot reach the server at ${ref.read(serverUrlProvider)}. '
          'Check your connection and the Server address below '
          '(emulator: ${AppConfig.emulatorBaseUrl}; physical device: your '
          "computer's LAN address, e.g. http://192.168.1.20:8000).";
    } on ApiException catch (e) {
      _error = e.status == 401 || e.status == 400 || e.status == 422
          ? 'Invalid email or password.'
          : 'Sign-in failed: ${e.message}';
    } catch (_) {
      _error = 'Sign-in failed. Please try again.';
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final expired =
        ref.watch(sessionProvider.select((s) => s.status)) ==
        SessionStatus.expired;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Icon(
                      Icons.handyman,
                      size: 48,
                      color: AppColors.primary,
                    ),
                    const SizedBox(height: 12),
                    Text(
                      AppConfig.appName,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'Sign in to see your assigned jobs',
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 24),
                    if (expired)
                      const _Notice(
                        icon: Icons.lock_clock,
                        text: 'Your session expired. Please sign in again.',
                        warning: true,
                      ),
                    if (_error != null)
                      _Notice(icon: Icons.error_outline, text: _error!),
                    TextFormField(
                      controller: _email,
                      keyboardType: TextInputType.emailAddress,
                      autofillHints: const [AutofillHints.username],
                      textInputAction: TextInputAction.next,
                      decoration: const InputDecoration(labelText: 'Email'),
                      validator: validateEmail,
                      enabled: !_busy,
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _password,
                      obscureText: _obscure,
                      autofillHints: const [AutofillHints.password],
                      textInputAction: TextInputAction.done,
                      onFieldSubmitted: (_) => _submit(),
                      decoration: InputDecoration(
                        labelText: 'Password',
                        suffixIcon: IconButton(
                          tooltip: _obscure ? 'Show password' : 'Hide password',
                          icon: Icon(
                            _obscure ? Icons.visibility : Icons.visibility_off,
                          ),
                          onPressed: () => setState(() => _obscure = !_obscure),
                        ),
                      ),
                      validator: validatePassword,
                      enabled: !_busy,
                    ),
                    const SizedBox(height: 20),
                    FilledButton(
                      onPressed: _busy ? null : _submit,
                      child: _busy
                          ? const SizedBox(
                              width: 22,
                              height: 22,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Sign in'),
                    ),
                    const SizedBox(height: 12),
                    ExpansionTile(
                      title: const Text('Server'),
                      subtitle: Text(ref.watch(serverUrlProvider)),
                      shape: const Border(),
                      collapsedShape: const Border(),
                      childrenPadding: const EdgeInsets.only(bottom: 8),
                      children: [
                        TextFormField(
                          key: _serverKey,
                          controller: _server,
                          keyboardType: TextInputType.url,
                          decoration: const InputDecoration(
                            labelText: 'Server address',
                            helperText: 'Emulator: http://10.0.2.2:8000. Physical device: http://<computer LAN IP>:8000',
                            helperMaxLines: 3,
                          ),
                          validator: validateServerUrl,
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            Expanded(
                              child: OutlinedButton(
                                onPressed: _resetServer,
                                child: const Text('Use default'),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: FilledButton.tonal(
                                onPressed: _saveServer,
                                child: const Text('Save server'),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice({required this.icon, required this.text, this.warning = false});
  final IconData icon;
  final String text;
  final bool warning;

  @override
  Widget build(BuildContext context) {
    final fg = warning ? AppColors.warningText : AppColors.danger;
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: warning ? AppColors.warningTint : AppColors.dangerTint,
        borderRadius: BorderRadius.circular(AppRadius.sm),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: fg, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(text, style: TextStyle(color: fg)),
          ),
        ],
      ),
    );
  }
}
