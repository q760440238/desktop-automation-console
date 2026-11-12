import 'package:flutter/material.dart';

class AppColors {
  static const bg = Color(0xFF0F1115);
  static const panel = Color(0xFF161A21);
  static const panel2 = Color(0xFF1B202A);
  static const panel3 = Color(0xFF212734);
  static const border = Color(0xFF242A35);
  static const borderSoft = Color(0xFF1E242E);
  static const text = Color(0xFFE6E9EF);
  static const textDim = Color(0xFFB3BCCD);
  static const muted = Color(0xFF7D879B);
  static const accent = Color(0xFF4F8CFF);
  static const accentDim = Color(0xFF2F5FB8);
  static const ok = Color(0xFF2ECC71);
  static const warn = Color(0xFFF5A623);
  static const danger = Color(0xFFFF4D4F);

  static Color risk(String r) => switch (r) {
    'high' => danger,
    'medium' => warn,
    _ => ok,
  };

  static Color riskBg(String r) => risk(r).withValues(alpha: 0.14);

  static Color status(String s) => switch (s) {
    'ok' => ok,
    'failed' => danger,
    'running' => accent,
    'approved' => accent,
    'pending' => warn,
    _ => muted,
  };

  static String statusLabel(String s) => switch (s) {
    'pending' => '待审批',
    'approved' => '已批准',
    'running' => '执行中',
    'ok' => '成功',
    'failed' => '失败',
    'rejected' => '已拒绝',
    'skipped' => '跳过',
    _ => s,
  };

  static String riskLabel(String r) => switch (r) {
    'high' => '高',
    'medium' => '中',
    _ => '低',
  };
}

ThemeData buildTheme() {
  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    fontFamily: 'Microsoft YaHei UI',
    scaffoldBackgroundColor: AppColors.bg,
    colorScheme: const ColorScheme.dark(
      surface: AppColors.panel,
      primary: AppColors.accent,
      onPrimary: Color(0xFF06101F),
      secondary: AppColors.ok,
      error: AppColors.danger,
      onSurface: AppColors.text,
    ),
  );

  return base.copyWith(
    textTheme: base.textTheme.apply(
      bodyColor: AppColors.text,
      displayColor: AppColors.text,
      fontSizeFactor: 0.98,
    ),
    dividerColor: AppColors.borderSoft,
    inputDecorationTheme: InputDecorationTheme(
      isDense: true,
      filled: true,
      fillColor: const Color(0xFF0B0E13),
      contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
      hintStyle: const TextStyle(color: Color(0xFF4D5666), fontSize: 12),
      labelStyle: const TextStyle(color: AppColors.muted, fontSize: 12),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(7),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(7),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(7),
        borderSide: const BorderSide(color: AppColors.accentDim),
      ),
    ),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(
        color: AppColors.panel3,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppColors.border),
      ),
      textStyle: const TextStyle(color: AppColors.textDim, fontSize: 11.5),
      waitDuration: const Duration(milliseconds: 400),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: AppColors.panel,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: AppColors.border),
      ),
    ),
    snackBarTheme: const SnackBarThemeData(
      backgroundColor: AppColors.panel3,
      contentTextStyle: TextStyle(color: AppColors.text, fontSize: 12.5),
      behavior: SnackBarBehavior.floating,
    ),
  );
}

/// 通用的小卡片容器。
class Panel extends StatelessWidget {
  const Panel({super.key, required this.child, this.padding});
  final Widget child;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: padding == null ? child : Padding(padding: padding!, child: child),
    );
  }
}

/// 区块标题（带序号）。
class SectionHead extends StatelessWidget {
  const SectionHead({
    super.key,
    required this.title,
    this.index,
    this.trailing,
  });
  final String title;
  final String? index;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        if (index != null) ...[
          Container(
            width: 18,
            height: 18,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: AppColors.panel3,
              borderRadius: BorderRadius.circular(5),
            ),
            child: Text(
              index!,
              style: const TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w700,
                color: AppColors.muted,
              ),
            ),
          ),
          const SizedBox(width: 8),
        ],
        Expanded(
          child: Text(
            title,
            style: const TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w600,
              color: AppColors.textDim,
            ),
          ),
        ),
        if (trailing != null) trailing!,
      ],
    );
  }
}
