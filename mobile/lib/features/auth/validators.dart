final _emailRe = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

String? validateEmail(String? v) {
  final s = (v ?? '').trim();
  if (s.isEmpty) return 'Enter your email.';
  if (!_emailRe.hasMatch(s)) return 'Enter a valid email address.';
  return null;
}

String? validatePassword(String? v) {
  if (v == null || v.isEmpty) return 'Enter your password.';
  return null;
}
