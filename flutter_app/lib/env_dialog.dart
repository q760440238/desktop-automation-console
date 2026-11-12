import 'package:flutter/material.dart';

import 'api.dart';
import 'app_state.dart';
import 'theme.dart';

/// 环境与集成：一键安装 Chrome MCP、查看已注册的 MCP 服务。
class EnvDialog extends StatefulWidget {
  const EnvDialog({super.key, required this.state});
  final AppState state;

  static Future<void> show(BuildContext context, AppState state) {
    return showDialog(
      context: context,
      builder: (_) => EnvDialog(state: state),
    );
  }

  @override
  State<EnvDialog> createState() => _EnvDialogState();
}

class _EnvDialogState extends State<EnvDialog> {
  Map<String, dynamic>? _status;
  bool _loading = true;
  bool _installing = false;
  bool _force = false;
  List<Map<String, dynamic>> _steps = const [];
  String? _result;
  bool _resultOk = false;

  static const _labels = <String, String>{
    'node': 'Node.js',
    'npm': 'npm',
    'chrome': 'Chrome / Edge',
    'package': 'Playwright MCP',
    'registered': 'Claude Code 注册',
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final s = await widget.state.setupStatus();
      if (!mounted) return;
      setState(() {
        _status = s;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _result = e.message;
        _resultOk = false;
      });
    }
  }

  Future<void> _install() async {
    setState(() {
      _installing = true;
      _steps = const [];
      _result = null;
    });
    try {
      final r = await widget.state.installChromeMcp(force: _force);
      if (!mounted) return;
      setState(() {
        _steps = ((r['steps'] as List?) ?? const [])
            .map((e) => Map<String, dynamic>.from(e as Map))
            .toList();
        _resultOk = r['ok'] == true;
        _result = (r['detail'] ?? '').toString();
      });
      await _load();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _resultOk = false;
        _result = e.message;
      });
    } finally {
      if (mounted) setState(() => _installing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final servers = ((_status?['servers'] as List?) ?? const [])
        .map((e) => e.toString())
        .toList();
    return Dialog(
      child: SizedBox(
        width: 640,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.fromLTRB(20, 16, 12, 12),
              decoration: const BoxDecoration(
                border: Border(bottom: BorderSide(color: AppColors.borderSoft)),
              ),
              child: Row(
                children: [
                  const Icon(
                    Icons.extension_outlined,
                    size: 17,
                    color: AppColors.accent,
                  ),
                  const SizedBox(width: 8),
                  const Text(
                    '环境与集成',
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                  ),
                  const Spacer(),
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(
                      Icons.close,
                      size: 18,
                      color: AppColors.muted,
                    ),
                  ),
                ],
              ),
            ),
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      'Chrome MCP',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      '给 Claude Code 装一个能操作浏览器的 MCP（复用本机 Chrome）。一键完成：装包 → 写入配置 → 真实握手验证。',
                      style: TextStyle(
                        fontSize: 11,
                        color: AppColors.muted,
                        height: 1.6,
                      ),
                    ),
                    const SizedBox(height: 10),
                    if (_loading)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 16),
                        child: Center(
                          child: SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: AppColors.muted,
                            ),
                          ),
                        ),
                      )
                    else
                      ...(_labels.entries.map((e) {
                        final item = (_status?[e.key] as Map?) ?? const {};
                        final ok = item['ok'] == true;
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 5),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Icon(
                                ok
                                    ? Icons.check_circle
                                    : Icons.remove_circle_outline,
                                size: 13,
                                color: ok ? AppColors.ok : AppColors.muted,
                              ),
                              const SizedBox(width: 6),
                              SizedBox(
                                width: 108,
                                child: Text(
                                  e.value,
                                  style: const TextStyle(
                                    fontSize: 11.5,
                                    color: AppColors.textDim,
                                  ),
                                ),
                              ),
                              Expanded(
                                child: Text(
                                  (item['detail'] ?? '—').toString(),
                                  style: const TextStyle(
                                    fontSize: 10.5,
                                    color: AppColors.muted,
                                    height: 1.4,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        );
                      })),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        SizedBox(
                          height: 26,
                          child: Checkbox(
                            value: _force,
                            onChanged: _installing
                                ? null
                                : (v) => setState(() => _force = v ?? false),
                            visualDensity: VisualDensity.compact,
                            materialTapTargetSize:
                                MaterialTapTargetSize.shrinkWrap,
                          ),
                        ),
                        const SizedBox(width: 4),
                        const Text(
                          '强制重新安装',
                          style: TextStyle(
                            fontSize: 11,
                            color: AppColors.muted,
                          ),
                        ),
                        const Spacer(),
                        FilledButton.icon(
                          onPressed: _installing ? null : _install,
                          icon: _installing
                              ? const SizedBox(
                                  width: 13,
                                  height: 13,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: Color(0xFF06101F),
                                  ),
                                )
                              : const Icon(Icons.download_done, size: 16),
                          label: Text(
                            _installing ? '安装中…' : '一键安装 Chrome MCP',
                            style: const TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          style: FilledButton.styleFrom(
                            backgroundColor: AppColors.accent,
                            foregroundColor: const Color(0xFF06101F),
                            padding: const EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 14,
                            ),
                          ),
                        ),
                      ],
                    ),
                    if (_installing)
                      const Padding(
                        padding: EdgeInsets.only(top: 8),
                        child: Text(
                          '正在安装并验证，通常 30 秒到 2 分钟，请不要关闭窗口…',
                          style: TextStyle(
                            fontSize: 10.5,
                            color: AppColors.muted,
                          ),
                        ),
                      ),
                    if (_steps.isNotEmpty) ...[
                      const SizedBox(height: 10),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 8,
                        ),
                        decoration: BoxDecoration(
                          color: const Color(0xFF0B0E13),
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(color: AppColors.borderSoft),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: _steps.map((s) {
                            final ok = s['ok'] == true;
                            return Padding(
                              padding: const EdgeInsets.only(bottom: 3),
                              child: Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Icon(
                                    ok ? Icons.check : Icons.close,
                                    size: 12,
                                    color: ok ? AppColors.ok : AppColors.danger,
                                  ),
                                  const SizedBox(width: 5),
                                  Text(
                                    '${s['name']}：',
                                    style: const TextStyle(
                                      fontSize: 10.5,
                                      color: AppColors.textDim,
                                    ),
                                  ),
                                  Expanded(
                                    child: Text(
                                      '${s['detail']}',
                                      style: const TextStyle(
                                        fontSize: 10.5,
                                        color: AppColors.muted,
                                        height: 1.4,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            );
                          }).toList(),
                        ),
                      ),
                    ],
                    if (_result != null) ...[
                      const SizedBox(height: 10),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 8,
                        ),
                        decoration: BoxDecoration(
                          color: (_resultOk ? AppColors.ok : AppColors.danger)
                              .withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(
                            color: (_resultOk ? AppColors.ok : AppColors.danger)
                                .withValues(alpha: 0.4),
                          ),
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(
                              _resultOk
                                  ? Icons.check_circle
                                  : Icons.error_outline,
                              size: 13,
                              color: _resultOk
                                  ? AppColors.ok
                                  : AppColors.danger,
                            ),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                _result!,
                                style: TextStyle(
                                  fontSize: 11,
                                  color: _resultOk
                                      ? const Color(0xFF9BF0C0)
                                      : const Color(0xFFFFB3B4),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                    const SizedBox(height: 18),
                    const Text(
                      '已注册的 MCP 服务',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: servers.isEmpty
                          ? [
                              const Text(
                                '未读取到配置',
                                style: TextStyle(
                                  fontSize: 11,
                                  color: AppColors.muted,
                                ),
                              ),
                            ]
                          : servers
                                .map(
                                  (s) => Container(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 8,
                                      vertical: 3,
                                    ),
                                    decoration: BoxDecoration(
                                      color: AppColors.panel2,
                                      borderRadius: BorderRadius.circular(5),
                                      border: Border.all(
                                        color: AppColors.border,
                                      ),
                                    ),
                                    child: Text(
                                      s,
                                      style: const TextStyle(
                                        fontSize: 10.5,
                                        color: AppColors.textDim,
                                      ),
                                    ),
                                  ),
                                )
                                .toList(),
                    ),
                  ],
                ),
              ),
            ),
            Container(
              padding: const EdgeInsets.fromLTRB(20, 10, 20, 12),
              decoration: const BoxDecoration(
                border: Border(top: BorderSide(color: AppColors.borderSoft)),
              ),
              child: Row(
                children: [
                  const Icon(
                    Icons.info_outline,
                    size: 13,
                    color: AppColors.muted,
                  ),
                  const SizedBox(width: 6),
                  const Expanded(
                    child: Text(
                      '装完需要重启 Claude Code 才会加载新的 MCP 服务。',
                      style: TextStyle(fontSize: 10.5, color: AppColors.muted),
                    ),
                  ),
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    style: TextButton.styleFrom(
                      foregroundColor: AppColors.muted,
                    ),
                    child: const Text('关闭', style: TextStyle(fontSize: 12)),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
