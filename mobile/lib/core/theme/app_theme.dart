import 'package:flutter/material.dart';

/// Design tokens shared with the FixFlow web app.
///
/// Fonts: the platform default (Roboto on Android) is used on purpose. No
/// runtime font fetching and no bundled TTFs, so the APK stays reproducible
/// offline. Heading weight (w700/w800) approximates Manrope.
class AppColors {
  AppColors._();
  static const primary = Color(0xFF0B7A5E);
  static const primaryDark = Color(0xFF0A5C47);
  static const deep = Color(0xFF103A30);
  static const ink = Color(0xFF13231D);
  static const text = Color(0xFF33443C);
  static const muted = Color(0xFF55655E);
  static const border = Color(0xFFDCE3DC);
  static const surface = Color(0xFFFFFFFF);
  static const canvas = Color(0xFFF1F4F0);
  static const primaryTint = Color(0xFFDDF0E8);
  static const danger = Color(0xFFC2410C);
  static const dangerTint = Color(0xFFFDEBDD);
  static const warning = Color(0xFFE8A23A);
  static const warningText = Color(0xFF8A5A00);
  static const warningTint = Color(0xFFFFF4D6);
}

class AppRadius {
  AppRadius._();
  static const sm = 8.0;
  static const md = 12.0;
  static const lg = 16.0;
}

ThemeData buildAppTheme() {
  final scheme =
      ColorScheme.fromSeed(
        seedColor: AppColors.primary,
        brightness: Brightness.light,
      ).copyWith(
        primary: AppColors.primary,
        onPrimary: Colors.white,
        primaryContainer: AppColors.primaryTint,
        onPrimaryContainer: AppColors.deep,
        secondary: AppColors.primaryDark,
        error: AppColors.danger,
        errorContainer: AppColors.dangerTint,
        onErrorContainer: AppColors.danger,
        surface: AppColors.surface,
        onSurface: AppColors.ink,
        outline: AppColors.border,
      );
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: AppColors.canvas,
  );
  final textTheme = base.textTheme
      .apply(bodyColor: AppColors.text, displayColor: AppColors.ink)
      .copyWith(
        titleLarge: const TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w800,
          color: AppColors.ink,
        ),
        titleMedium: const TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w700,
          color: AppColors.ink,
        ),
        titleSmall: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w700,
          color: AppColors.ink,
        ),
      );
  return base.copyWith(
    textTheme: textTheme,
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.deep,
      foregroundColor: Colors.white,
      elevation: 0,
      centerTitle: false,
    ),
    cardTheme: CardThemeData(
      color: AppColors.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.md),
        side: const BorderSide(color: AppColors.border),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.sm),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.sm),
        borderSide: const BorderSide(color: AppColors.border),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(48),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.sm),
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(48),
        foregroundColor: AppColors.primaryDark,
        side: const BorderSide(color: AppColors.border),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.sm),
        ),
      ),
    ),
    dividerTheme: const DividerThemeData(color: AppColors.border, space: 1),
    tabBarTheme: const TabBarThemeData(
      labelColor: Colors.white,
      unselectedLabelColor: Color(0xFFBFD8CE),
      indicatorColor: Colors.white,
    ),
  );
}
