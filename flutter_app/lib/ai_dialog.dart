import 'dart:async';

import 'package:flutter/material.dart';

import 'api.dart';
import 'app_state.dart';
import 'theme.dart';

/// AI 模型设置：服务商 / 地址 / Key / 模型 / 思考深度。
class AiSettingsDialog extends StatefulWidget {
  const AiSettingsDialog({super.key, required this.state});
  final AppState state;

  static Future<void> show(BuildContext context, AppState state) {
    return showDialog(
      context: context,
      barrierDismissible: true,
      builder: (_) => AiSettingsDialog(state: state),
    );
  }

  @override
  State<AiSettingsDialog> createState() => _AiSettingsDialogState();
}

class _AiSettingsDialogState extends State<AiSettingsDialog> {
  final _baseCtrl = TextEditingController();
  final _keyCtrl = TextEditingController();
  final _modelCtrl = TextEditingController();

  String _provider = 'custom';
  String _thinking = 'medium';
  bool _obscure = true;
  bool _testing = false;
  bool _saving = false;
  String? _testMsg;
  bool _testOk = false;
  bool _clearKey = false;

  // 模型列表：填完地址 + Key 自动拉取，供下拉选择
  final List<String> _models = [];
  bool _loadingModels = false;
  bool _modelsOk = false;
  String? _modelsMsg;
  Timer? _debounce;
  String _lastBase = '';
  String _lastKey = '';

  List<ProviderPreset> get _presets => widget.state.ai?.providers ?? const [];

  @override
  void initState() {
    super.initState();
    final ai = widget.state.ai;
    _provider = ai?.provider ?? 'custom';
    _baseCtrl.text = ai?.baseUrl ?? '';
    _modelCtrl.text = ai?.model ?? '';
    _thinking = ai?.thinking ?? 'medium';

    _baseCtrl.addListener(_onCredsChanged);
    _keyCtrl.addListener(_onCredsChanged);
    // 打开弹窗就尝试拉一次（地址已填好、Key 已保存的情况）
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_baseCtrl.text.trim().isNotEmpty) _fetchModels();
    });
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _baseCtrl.removeListener(_onCredsChanged);
    _keyCtrl.removeListener(_onCredsChanged);
    _baseCtrl.dispose();
    _keyCtrl.dispose();
    _modelCtrl.dispose();
    super.dispose();
  }

  void _onCredsChanged() {
    final base = _baseCtrl.text.trim();
    if (base.isEmpty) return;
    if (base == _lastBase && _keyCtrl.text.trim() == _lastKey) return;
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 900), _fetchModels);
  }

  Future<void> _fetchModels() async {
    final base = _baseCtrl.text.trim();
    if (base.isEmpty || _loadingModels) return;
    final key = _keyCtrl.text.trim();
    final hasSaved = widget.state.ai?.apiKeySet == true;
    final local = base.contains('127.0.0.1') || base.contains('localhost');
    if (key.isEmpty && !hasSaved && !local) {
      setState(() {
        _modelsOk = false;
        _modelsMsg = '填写 API Key 后会自动获取模型列表';
      });
      return;
    }
    setState(() {
      _loadingModels = true;
      _modelsOk = false;
      _modelsMsg = '正在获取模型列表…';
    });
    try {
      final r = await widget.state.fetchModels(base, key);
      if (!mounted) return;
      final list = ((r['models'] as List?) ?? const [])
          .map((e) => e is Map ? (e['id'] ?? '').toString() : e.toString())
          .where((s) => s.isNotEmpty)
          .toList();
      _lastBase = base;
      _lastKey = key;
      setState(() {
        _models
          ..clear()
          ..addAll(list);
        _modelsOk = r['ok'] == true;
        _modelsMsg = (r['detail'] ?? '').toString();
        if (!_modelsOk && list.isEmpty) {
          _modelsMsg = '${_modelsMsg ?? '获取失败'}（也可以手动输入模型名）';
        }
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _modelsOk = false;
        _modelsMsg = e.message;
      });
    } finally {
      if (mounted) setState(() => _loadingModels = false);
    }
  }

  ProviderPreset? get _preset {
    for (final p in _presets) {
      if (p.key == _provider) return p;
    }
    return null;
  }

  void _applyPreset(String? key) {
    if (key == null) return;
    setState(() {
      _provider = key;
      final p = _preset;
      if (p != null && p.baseUrl.isNotEmpty) _baseCtrl.text = p.baseUrl;
      if (p != null && p.models.isNotEmpty) _modelCtrl.text = p.models.first;
    });
  }

  Future<void> _test() async {
    setState(() {
      _testing = true;
      _testMsg = null;
    });
    try {
      final r = await widget.state.testAi({
        'base_url': _baseCtrl.text.trim(),
        'model': _modelCtrl.text.trim(),
        if (_keyCtrl.text.trim().isNotEmpty) 'api_key': _keyCtrl.text.trim(),
      });
      if (!mounted) return;
      final list = ((r['models'] as List?) ?? const [])
          .map((e) => e.toString())
          .where((s) => s.isNotEmpty)
          .toList();
      setState(() {
        _testOk = r['ok'] == true;
        _testMsg = (r['detail'] ?? '').toString();
        if (list.isNotEmpty) {
          _models
            ..clear()
            ..addAll(list);
          _modelsOk = true;
        }
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _testOk = false;
        _testMsg = e.message;
      });
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await widget.state.saveAi({
        'provider': _provider,
        'base_url': _baseCtrl.text.trim(),
        'model': _modelCtrl.text.trim(),
        'thinking': _thinking,
        if (_clearKey) 'api_key': '-',
        if (!_clearKey && _keyCtrl.text.trim().isNotEmpty)
          'api_key': _keyCtrl.text.trim(),
      });
      if (!mounted) return;
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '已保存：${_modelCtrl.text.trim()} · 思考深度 ${_thinkingLabel(_thinking)}',
          ),
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _testOk = false;
        _testMsg = e.message;
      });
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  String _thinkingLabel(String v) => switch (v) {
    'off' => '关闭',
    'low' => '低',
    'high' => '高',
    _ => '中',
  };

  @override
  Widget build(BuildContext context) {
    final ai = widget.state.ai;
    return Dialog(
      child: SizedBox(
        width: 620,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 标题
            Container(
              padding: const EdgeInsets.fromLTRB(20, 16, 12, 12),
              decoration: const BoxDecoration(
                border: Border(bottom: BorderSide(color: AppColors.borderSoft)),
              ),
              child: Row(
                children: [
                  const Icon(
                    Icons.auto_awesome,
                    size: 17,
                    color: AppColors.accent,
                  ),
                  const SizedBox(width: 8),
                  const Text(
                    'AI 模型设置',
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
                    tooltip: '关闭',
                  ),
                ],
              ),
            ),
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      '接入任意 OpenAI 兼容接口，用于生成私信/消息文案。配置只保存在本机。',
                      style: TextStyle(fontSize: 11.5, color: AppColors.muted),
                    ),
                    const SizedBox(height: 16),

                    _label('服务商'),
                    _dropdown(),
                    const SizedBox(height: 14),

                    _label('API 地址'),
                    TextField(
                      controller: _baseCtrl,
                      style: const TextStyle(
                        fontSize: 12.5,
                        fontFamily: 'Consolas',
                      ),
                      decoration: const InputDecoration(
                        hintText: 'https://api.deepseek.com/v1',
                        prefixIcon: Icon(
                          Icons.link,
                          size: 16,
                          color: AppColors.muted,
                        ),
                        prefixIconConstraints: BoxConstraints(minWidth: 36),
                      ),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      '需以 /v1 结尾（部分网关用 /openai/v1）',
                      style: TextStyle(fontSize: 10.5, color: AppColors.muted),
                    ),
                    const SizedBox(height: 14),

                    _label('API Key'),
                    TextField(
                      controller: _keyCtrl,
                      obscureText: _obscure,
                      style: const TextStyle(
                        fontSize: 12.5,
                        fontFamily: 'Consolas',
                      ),
                      decoration: InputDecoration(
                        hintText: ai?.apiKeySet == true
                            ? '已保存 ••••••••${ai?.apiKeyTail ?? ''}（留空则不修改）'
                            : 'sk-...',
                        prefixIcon: const Icon(
                          Icons.key,
                          size: 16,
                          color: AppColors.muted,
                        ),
                        prefixIconConstraints: const BoxConstraints(
                          minWidth: 36,
                        ),
                        suffixIcon: IconButton(
                          icon: Icon(
                            _obscure ? Icons.visibility_off : Icons.visibility,
                            size: 16,
                            color: AppColors.muted,
                          ),
                          onPressed: () => setState(() => _obscure = !_obscure),
                          tooltip: _obscure ? '显示' : '隐藏',
                        ),
                      ),
                    ),
                    if (ai?.apiKeySet == true)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Row(
                          children: [
                            const Icon(
                              Icons.check_circle,
                              size: 12,
                              color: AppColors.ok,
                            ),
                            const SizedBox(width: 4),
                            Text(
                              '已配置密钥（末四位 ${ai?.apiKeyTail}）',
                              style: const TextStyle(
                                fontSize: 10.5,
                                color: AppColors.muted,
                              ),
                            ),
                            const Spacer(),
                            TextButton(
                              onPressed: () =>
                                  setState(() => _clearKey = !_clearKey),
                              style: TextButton.styleFrom(
                                minimumSize: Size.zero,
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 6,
                                ),
                                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              ),
                              child: Text(
                                _clearKey ? '撤销清除' : '清除密钥',
                                style: TextStyle(
                                  fontSize: 10.5,
                                  color: _clearKey
                                      ? AppColors.accent
                                      : AppColors.danger,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    const SizedBox(height: 14),

                    _label('模型', trailing: _modelTrailing()),
                    _modelField(),
                    if (_modelsMsg != null) ...[
                      const SizedBox(height: 5),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(
                            _modelsOk ? Icons.check_circle : Icons.info_outline,
                            size: 12,
                            color: _modelsOk ? AppColors.ok : AppColors.muted,
                          ),
                          const SizedBox(width: 4),
                          Expanded(
                            child: Text(
                              _modelsMsg!,
                              style: TextStyle(
                                fontSize: 10.5,
                                color: _modelsOk
                                    ? const Color(0xFF9BF0C0)
                                    : AppColors.muted,
                                height: 1.4,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                    if ((_preset?.models ?? const []).isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: _preset!.models.map((m) {
                          final active = _modelCtrl.text == m;
                          return GestureDetector(
                            onTap: () => setState(() => _modelCtrl.text = m),
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                                vertical: 3,
                              ),
                              decoration: BoxDecoration(
                                color: active
                                    ? AppColors.accent.withValues(alpha: 0.14)
                                    : AppColors.panel2,
                                borderRadius: BorderRadius.circular(5),
                                border: Border.all(
                                  color: active
                                      ? AppColors.accentDim
                                      : AppColors.border,
                                ),
                              ),
                              child: Text(
                                m,
                                style: TextStyle(
                                  fontSize: 10.5,
                                  color: active
                                      ? const Color(0xFF9FC0FF)
                                      : AppColors.textDim,
                                ),
                              ),
                            ),
                          );
                        }).toList(),
                      ),
                    ],
                    const SizedBox(height: 18),

                    _label('思考深度'),
                    SegmentedButton<String>(
                      showSelectedIcon: false,
                      style: SegmentedButton.styleFrom(
                        backgroundColor: AppColors.panel2,
                        foregroundColor: AppColors.textDim,
                        selectedBackgroundColor: AppColors.accent.withValues(
                          alpha: 0.16,
                        ),
                        selectedForegroundColor: const Color(0xFF9FC0FF),
                        side: const BorderSide(color: AppColors.border),
                        visualDensity: VisualDensity.compact,
                      ),
                      segments: const [
                        ButtonSegment(
                          value: 'off',
                          label: Text('关闭', style: TextStyle(fontSize: 12)),
                        ),
                        ButtonSegment(
                          value: 'low',
                          label: Text('低', style: TextStyle(fontSize: 12)),
                        ),
                        ButtonSegment(
                          value: 'medium',
                          label: Text('中', style: TextStyle(fontSize: 12)),
                        ),
                        ButtonSegment(
                          value: 'high',
                          label: Text('高', style: TextStyle(fontSize: 12)),
                        ),
                      ],
                      selected: {_thinking},
                      onSelectionChanged: (s) =>
                          setState(() => _thinking = s.first),
                    ),
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.panel2,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: AppColors.borderSoft),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(
                            Icons.info_outline,
                            size: 13,
                            color: AppColors.muted,
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(
                              _thinkingHint(_thinking),
                              style: const TextStyle(
                                fontSize: 10.5,
                                color: AppColors.muted,
                                height: 1.5,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (_testMsg != null) ...[
                      const SizedBox(height: 14),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 8,
                        ),
                        decoration: BoxDecoration(
                          color: (_testOk ? AppColors.ok : AppColors.danger)
                              .withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(
                            color: (_testOk ? AppColors.ok : AppColors.danger)
                                .withValues(alpha: 0.4),
                          ),
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(
                              _testOk
                                  ? Icons.check_circle
                                  : Icons.error_outline,
                              size: 14,
                              color: _testOk ? AppColors.ok : AppColors.danger,
                            ),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                _testMsg!,
                                style: TextStyle(
                                  fontSize: 11.5,
                                  color: _testOk
                                      ? const Color(0xFF9BF0C0)
                                      : const Color(0xFFFFB3B4),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
            Container(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 14),
              decoration: const BoxDecoration(
                border: Border(top: BorderSide(color: AppColors.borderSoft)),
              ),
              child: Row(
                children: [
                  OutlinedButton.icon(
                    onPressed: _testing ? null : _test,
                    icon: _testing
                        ? const SizedBox(
                            width: 12,
                            height: 12,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: AppColors.muted,
                            ),
                          )
                        : const Icon(Icons.wifi_tethering, size: 15),
                    label: Text(
                      _testing ? '测试中…' : '测试连接',
                      style: const TextStyle(fontSize: 12),
                    ),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.textDim,
                      side: const BorderSide(color: AppColors.border),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 14,
                      ),
                    ),
                  ),
                  const Spacer(),
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    style: TextButton.styleFrom(
                      foregroundColor: AppColors.muted,
                    ),
                    child: const Text('取消', style: TextStyle(fontSize: 12)),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: _saving ? null : _save,
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.accent,
                      foregroundColor: const Color(0xFF06101F),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 20,
                        vertical: 14,
                      ),
                    ),
                    child: Text(
                      _saving ? '保存中…' : '保存',
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _thinkingHint(String v) => switch (v) {
    'off' => '不请求推理过程，响应最快、最省 token，适合简单的一句话通知。',
    'low' => '轻微推理，速度快，适合常规问候与确认类消息。',
    'high' => '深度推理，写出来的话更有分寸，但更慢、更贵，适合重要客户的首次触达。',
    _ => '平衡模式（推荐）：在措辞上更周到，同时保持可接受的延迟与成本。',
  };

  Widget _modelTrailing() {
    if (_loadingModels) {
      return const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: 11,
            height: 11,
            child: CircularProgressIndicator(
              strokeWidth: 1.6,
              color: AppColors.muted,
            ),
          ),
          SizedBox(width: 5),
          Text(
            '获取中…',
            style: TextStyle(fontSize: 10.5, color: AppColors.muted),
          ),
        ],
      );
    }
    return TextButton.icon(
      onPressed: _fetchModels,
      icon: const Icon(Icons.refresh, size: 13, color: AppColors.muted),
      label: Text(
        _models.isEmpty ? '获取模型' : '重新获取',
        style: const TextStyle(fontSize: 10.5, color: AppColors.muted),
      ),
      style: TextButton.styleFrom(
        minimumSize: Size.zero,
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
    );
  }

  Widget _modelField() {
    final theme = InputDecorationTheme(
      isDense: true,
      filled: true,
      fillColor: const Color(0xFF0B0E13),
      contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 14),
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
    );
    return DropdownMenu<String>(
      controller: _modelCtrl,
      initialSelection: _models.contains(_modelCtrl.text)
          ? _modelCtrl.text
          : null,
      enableFilter: true,
      requestFocusOnTap: true,
      menuHeight: 320,
      expandedInsets: EdgeInsets.zero,
      hintText: _models.isEmpty
          ? 'deepseek-chat'
          : '从 ${_models.length} 个模型中选择',
      leadingIcon: const Icon(Icons.memory, size: 16, color: AppColors.muted),
      textStyle: const TextStyle(
        fontSize: 12.5,
        fontFamily: 'Consolas',
        color: AppColors.text,
      ),
      inputDecorationTheme: theme,
      dropdownMenuEntries: _models
          .map((m) => DropdownMenuEntry<String>(value: m, label: m))
          .toList(),
      onSelected: (_) => setState(() {}),
    );
  }

  Widget _label(String text, {Widget? trailing}) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Row(
      children: [
        Text(
          text,
          style: const TextStyle(
            fontSize: 11.5,
            color: AppColors.textDim,
            fontWeight: FontWeight.w500,
          ),
        ),
        const Spacer(),
        if (trailing != null) trailing,
      ],
    ),
  );

  Widget _dropdown() {
    return Container(
      height: 38,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF0B0E13),
        borderRadius: BorderRadius.circular(7),
        border: Border.all(color: AppColors.border),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: _presets.any((p) => p.key == _provider) ? _provider : null,
          isExpanded: true,
          dropdownColor: AppColors.panel3,
          icon: const Icon(Icons.expand_more, size: 16, color: AppColors.muted),
          hint: const Text(
            '选择服务商',
            style: TextStyle(fontSize: 12, color: Color(0xFF4D5666)),
          ),
          style: const TextStyle(fontSize: 12.5, color: AppColors.text),
          items: _presets
              .map(
                (p) => DropdownMenuItem<String>(
                  value: p.key,
                  child: Text(p.name, style: const TextStyle(fontSize: 12.5)),
                ),
              )
              .toList(),
          onChanged: _applyPreset,
        ),
      ),
    );
  }
}
