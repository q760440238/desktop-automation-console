import 'package:flutter/material.dart';

import 'ai_dialog.dart';
import 'api.dart';
import 'app_state.dart';
import 'env_dialog.dart';
import 'panels.dart';
import 'theme.dart';

const String kBackend = 'http://127.0.0.1:18765';

void main() {
  runApp(const ConsoleApp());
}

class ConsoleApp extends StatefulWidget {
  const ConsoleApp({super.key});

  @override
  State<ConsoleApp> createState() => _ConsoleAppState();
}

class _ConsoleAppState extends State<ConsoleApp> {
  late final AppState _state;

  @override
  void initState() {
    super.initState();
    _state = AppState(ApiClient(baseUrl: kBackend));
    _state.start();
  }

  @override
  void dispose() {
    _state.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '桌面自动化控制台',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: AnimatedBuilder(
        animation: _state,
        builder: (context, _) => _Shell(state: _state),
      ),
    );
  }
}

class _Shell extends StatelessWidget {
  const _Shell({required this.state});
  final AppState state;

  void _toast(BuildContext context, String? msg) {
    if (msg == null) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          _TopBar(state: state),
          // 注意：这两个横幅必须占位（用 SizedBox.shrink 兜底），
          // 否则条件插入会让下面的 Expanded 子树位置变化，导致整棵任务面板被重建、输入内容丢失。
          if (state.connError != null)
            _connBanner(context)
          else
            const SizedBox.shrink(),
          if (state.panic) _panicBanner(context) else const SizedBox.shrink(),
          if (state.autoRunning)
            _autoBanner(context)
          else
            const SizedBox.shrink(),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  SizedBox(width: 300, child: PlatformRail(state: state)),
                  const SizedBox(width: 12),
                  Expanded(flex: 11, child: TaskForm(state: state)),
                  const SizedBox(width: 12),
                  Expanded(flex: 10, child: ExecPanel(state: state)),
                ],
              ),
            ),
          ),
          LogBar(state: state),
        ],
      ),
    );
  }

  Widget _connBanner(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: AppColors.danger.withValues(alpha: 0.12),
      child: Row(
        children: [
          const Icon(Icons.cloud_off, size: 14, color: AppColors.danger),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              state.connError!,
              style: const TextStyle(fontSize: 11.5, color: Color(0xFFFFB3B4)),
            ),
          ),
          TextButton(
            onPressed: state.refreshAll,
            child: const Text('重试', style: TextStyle(fontSize: 11.5)),
          ),
        ],
      ),
    );
  }

  Widget _autoBanner(BuildContext context) {
    final ap = state.autopilot!;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: AppColors.warn.withValues(alpha: 0.12),
      child: Row(
        children: [
          const Icon(Icons.autorenew, size: 14, color: AppColors.warn),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              '无限模式运行中 · 第 ${ap['round']} 轮 · 已发 ${ap['sent'] ?? 0} · ${ap['phase'] ?? ''}',
              style: const TextStyle(fontSize: 11.5, color: Color(0xFFF0BB6B)),
            ),
          ),
          OutlinedButton(
            onPressed: () => state.stopAuto(),
            style: OutlinedButton.styleFrom(
              side: BorderSide(color: AppColors.warn.withValues(alpha: 0.6)),
              foregroundColor: const Color(0xFFF0BB6B),
              visualDensity: VisualDensity.compact,
            ),
            child: const Text('停止', style: TextStyle(fontSize: 11.5)),
          ),
        ],
      ),
    );
  }

  Widget _panicBanner(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: AppColors.danger.withValues(alpha: 0.14),
      child: Row(
        children: [
          const Icon(Icons.pan_tool, size: 14, color: AppColors.danger),
          const SizedBox(width: 8),
          const Expanded(
            child: Text(
              '已急停：所有任务已中止，新任务无法启动。确认现场安全后解除。',
              style: TextStyle(fontSize: 11.5, color: Color(0xFFFFB3B4)),
            ),
          ),
          OutlinedButton(
            onPressed: () async {
              final err = await state.togglePanic(false);
              if (err != null && context.mounted) _toast(context, err);
            },
            style: OutlinedButton.styleFrom(
              side: const BorderSide(color: AppColors.danger),
              foregroundColor: const Color(0xFFFFB3B4),
              visualDensity: VisualDensity.compact,
            ),
            child: const Text('解除急停', style: TextStyle(fontSize: 11.5)),
          ),
        ],
      ),
    );
  }
}

/* ------------------------------------------------------------------ 顶栏 */
class _TopBar extends StatelessWidget {
  const _TopBar({required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final ai = state.ai;
    final needsKey =
        ai != null &&
        !ai.apiKeySet &&
        !ai.baseUrl.contains('127.0.0.1') &&
        !ai.baseUrl.contains('localhost');
    final aiReady =
        ai != null && ai.baseUrl.isNotEmpty && ai.model.isNotEmpty && !needsKey;
    return Container(
      height: 62,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF171C24), Color(0xFF12161C)],
        ),
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: [
          // 品牌
          Container(
            width: 34,
            height: 34,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: AppColors.accent.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(9),
              border: Border.all(
                color: AppColors.accent.withValues(alpha: 0.3),
              ),
            ),
            child: const Icon(
              Icons.desktop_windows_outlined,
              size: 18,
              color: AppColors.accent,
            ),
          ),
          const SizedBox(width: 10),
          Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '桌面自动化控制台',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
              ),
              Text(
                '${state.platforms.isEmpty ? 10 : state.platforms.length} 个渠道 · 本地运行',
                style: const TextStyle(fontSize: 10.5, color: AppColors.muted),
              ),
            ],
          ),
          const SizedBox(width: 24),

          // 模式
          SegmentedButton<String>(
            showSelectedIcon: false,
            style: SegmentedButton.styleFrom(
              backgroundColor: const Color(0xFF0C0F14),
              foregroundColor: AppColors.textDim,
              selectedBackgroundColor: AppColors.accent.withValues(alpha: 0.16),
              selectedForegroundColor: const Color(0xFF9FC0FF),
              side: const BorderSide(color: AppColors.border),
              visualDensity: VisualDensity.compact,
              padding: const EdgeInsets.symmetric(horizontal: 10),
            ),
            segments: const [
              ButtonSegment(
                value: 'dry_run',
                label: Text('只出计划', style: TextStyle(fontSize: 11.5)),
              ),
              ButtonSegment(
                value: 'confirm',
                label: Text('确认后执行', style: TextStyle(fontSize: 11.5)),
              ),
              ButtonSegment(
                value: 'auto',
                label: Text('自动执行', style: TextStyle(fontSize: 11.5)),
              ),
            ],
            selected: {state.mode},
            onSelectionChanged: (s) async {
              final err = await state.setMode(s.first);
              if (err != null && context.mounted) {
                ScaffoldMessenger.of(
                  context,
                ).showSnackBar(SnackBar(content: Text(err)));
              }
            },
          ),
          const SizedBox(width: 16),

          // 演练开关
          Row(
            children: [
              Switch(
                value: state.simulation,
                onChanged: (v) async {
                  final err = await state.setSimulation(v);
                  if (err != null && context.mounted) {
                    ScaffoldMessenger.of(
                      context,
                    ).showSnackBar(SnackBar(content: Text(err)));
                  }
                },
                activeThumbColor: AppColors.warn,
                activeTrackColor: AppColors.warn.withValues(alpha: 0.25),
              ),
              const Text(
                '演练模式',
                style: TextStyle(fontSize: 11.5, color: AppColors.textDim),
              ),
            ],
          ),

          const Spacer(),

          // 统计
          _stat('${state.health?.running ?? 0}', '运行中'),
          const SizedBox(width: 14),
          _stat('${state.health?.pending ?? 0}', '待审批'),
          const SizedBox(width: 16),

          // 环境与集成（Chrome MCP 一键安装）
          IconButton(
            onPressed: () => EnvDialog.show(context, state),
            icon: const Icon(Icons.extension_outlined, size: 17),
            color: AppColors.muted,
            tooltip: '环境与集成（一键安装 Chrome MCP）',
            style: IconButton.styleFrom(
              side: const BorderSide(color: AppColors.border),
              padding: const EdgeInsets.all(10),
            ),
          ),
          const SizedBox(width: 8),

          // AI 设置
          Tooltip(
            message: aiReady
                ? '服务商 ${ai.provider} · 模型 ${ai.model} · 思考深度 ${_thinkingLabel(ai.thinking)}'
                : '尚未配置 AI 模型',
            child: OutlinedButton.icon(
              onPressed: () => AiSettingsDialog.show(context, state),
              icon: Icon(
                aiReady ? Icons.auto_awesome : Icons.settings_outlined,
                size: 15,
                color: aiReady ? AppColors.accent : AppColors.muted,
              ),
              label: Text(
                aiReady ? ai.model : 'AI 设置',
                style: TextStyle(
                  fontSize: 11.5,
                  color: aiReady ? const Color(0xFF9FC0FF) : AppColors.textDim,
                ),
              ),
              style: OutlinedButton.styleFrom(
                side: BorderSide(
                  color: aiReady
                      ? AppColors.accent.withValues(alpha: 0.45)
                      : AppColors.border,
                ),
                backgroundColor: aiReady
                    ? AppColors.accent.withValues(alpha: 0.08)
                    : Colors.transparent,
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 12,
                ),
              ),
            ),
          ),
          const SizedBox(width: 10),

          // 急停
          FilledButton(
            onPressed: () async {
              if (state.panic) {
                await state.togglePanic(false);
                return;
              }
              final ok = await showDialog<bool>(
                context: context,
                builder: (ctx) => AlertDialog(
                  title: const Text('确认急停？', style: TextStyle(fontSize: 14)),
                  content: const Text(
                    '急停会立刻中止所有正在运行的任务，并阻止新任务启动。',
                    style: TextStyle(fontSize: 12.5, height: 1.7),
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(ctx, false),
                      child: const Text('取消'),
                    ),
                    FilledButton(
                      onPressed: () => Navigator.pop(ctx, true),
                      style: FilledButton.styleFrom(
                        backgroundColor: AppColors.danger,
                      ),
                      child: const Text('急停'),
                    ),
                  ],
                ),
              );
              if (ok == true) await state.togglePanic(true);
            },
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.danger.withValues(
                alpha: state.panic ? 0.55 : 0.12,
              ),
              foregroundColor: state.panic
                  ? Colors.white
                  : const Color(0xFFFF8A8C),
              side: BorderSide(color: AppColors.danger.withValues(alpha: 0.5)),
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
            ),
            child: Text(
              state.panic ? '已急停' : '急停',
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                letterSpacing: 1,
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _thinkingLabel(String v) => switch (v) {
    'off' => '关闭',
    'low' => '低',
    'high' => '高',
    _ => '中',
  };

  Widget _stat(String value, String label) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text(
          value,
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            fontFeatures: [FontFeature.tabularFigures()],
          ),
        ),
        Text(
          label,
          style: const TextStyle(fontSize: 10.5, color: AppColors.muted),
        ),
      ],
    );
  }
}
