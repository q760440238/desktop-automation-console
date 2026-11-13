import 'dart:convert';

import 'package:flutter/material.dart';

import 'api.dart';
import 'app_state.dart';
import 'theme.dart';

/* ------------------------------------------------------------------ 平台栏 */
class PlatformRail extends StatelessWidget {
  const PlatformRail({super.key, required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final platforms = state.platforms;
    return Panel(
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(13, 10, 8, 10),
            child: Row(
              children: [
                const Text(
                  '平台',
                  style: TextStyle(
                    fontSize: 11,
                    letterSpacing: 1.2,
                    color: AppColors.textDim,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const Spacer(),
                IconButton(
                  onPressed: state.refreshHealth,
                  icon: const Icon(
                    Icons.refresh,
                    size: 15,
                    color: AppColors.muted,
                  ),
                  tooltip: '重新探测连接状态',
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(
                    minWidth: 26,
                    minHeight: 26,
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1, color: AppColors.borderSoft),
          Expanded(
            child: platforms.isEmpty
                ? const Center(
                    child: Text(
                      '正在读取平台状态…',
                      style: TextStyle(fontSize: 11.5, color: AppColors.muted),
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.all(8),
                    itemCount: platforms.length,
                    itemBuilder: (_, i) => _platformCard(context, platforms[i]),
                  ),
          ),
          const Divider(height: 1, color: AppColors.borderSoft),
          const Padding(
            padding: EdgeInsets.fromLTRB(13, 10, 13, 12),
            child: Text(
              '网页平台首次使用需在浏览器里登录一次，登录态保存在本机 data/browser_profiles/。',
              style: TextStyle(
                fontSize: 10.5,
                color: AppColors.muted,
                height: 1.5,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _platformCard(BuildContext context, PlatformInfo p) {
    final selected = state.platform == p.key;
    final color = Color(p.color);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(8),
          onTap: () => state.selectPlatform(p.key),
          child: Container(
            padding: const EdgeInsets.fromLTRB(13, 8, 9, 8),
            decoration: BoxDecoration(
              color: selected
                  ? Color.alphaBlend(
                      color.withValues(alpha: 0.1),
                      AppColors.panel2,
                    )
                  : AppColors.panel2,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: selected ? color : AppColors.border),
            ),
            child: Stack(
              children: [
                Positioned(
                  left: -13,
                  top: -8,
                  bottom: -8,
                  child: Container(
                    width: 3,
                    color: color.withValues(alpha: selected ? 1 : 0.55),
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 19,
                          height: 19,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: color,
                            borderRadius: BorderRadius.circular(5),
                          ),
                          child: Text(
                            p.name.substring(0, 1),
                            style: const TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF0B0D11),
                            ),
                          ),
                        ),
                        const SizedBox(width: 7),
                        Text(
                          p.name,
                          style: const TextStyle(
                            fontSize: 12.5,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 4,
                            vertical: 0,
                          ),
                          decoration: BoxDecoration(
                            border: Border.all(color: AppColors.border),
                            borderRadius: BorderRadius.circular(3),
                          ),
                          child: Text(
                            p.isDesktop ? '桌面端' : '网页端',
                            style: const TextStyle(
                              fontSize: 9.5,
                              color: AppColors.muted,
                            ),
                          ),
                        ),
                        const Spacer(),
                        Container(
                          width: 6,
                          height: 6,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: p.health.ready
                                ? AppColors.ok
                                : const Color(0xFF4A5262),
                          ),
                        ),
                      ],
                    ),
                    Padding(
                      padding: const EdgeInsets.only(left: 26, top: 3),
                      child: Text(
                        p.health.detail.isEmpty ? '未知状态' : p.health.detail,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 10.5,
                          color: AppColors.muted,
                        ),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Padding(
                      padding: const EdgeInsets.only(left: 26),
                      child: Row(
                        children: [
                          _miniBtn(
                            p.isDesktop ? '启动应用' : '打开浏览器登录',
                            () => _open(context, p),
                          ),
                          const SizedBox(width: 5),
                          _miniBtn('探测', () => _probe(context, p)),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _miniBtn(String label, VoidCallback onTap) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(5),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
        decoration: BoxDecoration(
          color: const Color(0xFF0E1218),
          borderRadius: BorderRadius.circular(5),
          border: Border.all(color: AppColors.border),
        ),
        child: Text(
          label,
          style: const TextStyle(fontSize: 10.5, color: AppColors.textDim),
        ),
      ),
    );
  }

  Future<void> _open(BuildContext context, PlatformInfo p) async {
    final msg = await state.openPlatform(p.key);
    if (!context.mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(msg ?? '已打开')));
  }

  Future<void> _probe(BuildContext context, PlatformInfo p) async {
    final data = await state.probePlatform(p.key);
    if (!context.mounted) return;
    showDialog(
      context: context,
      builder: (_) => Dialog(
        child: SizedBox(
          width: 640,
          height: 460,
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
                child: Row(
                  children: [
                    Text(
                      '控件探测 · ${p.name}',
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const Spacer(),
                    IconButton(
                      icon: const Icon(
                        Icons.close,
                        size: 18,
                        color: AppColors.muted,
                      ),
                      onPressed: () => Navigator.of(context).pop(),
                    ),
                  ],
                ),
              ),
              const Divider(height: 1, color: AppColors.borderSoft),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(14),
                  child: SelectableText(
                    const JsonEncoder.withIndent('  ').convert(data),
                    style: const TextStyle(
                      fontSize: 10.5,
                      fontFamily: 'Consolas',
                      color: AppColors.textDim,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/* ------------------------------------------------------------------ 任务栏 */
class TaskForm extends StatefulWidget {
  const TaskForm({super.key, required this.state});
  final AppState state;

  @override
  State<TaskForm> createState() => _TaskFormState();
}

class _TaskFormState extends State<TaskForm> {
  final _targets = TextEditingController();
  final _message = TextEditingController();
  String? _status;

  // ---- 按方向找 ----
  bool _byBrief = false;
  final _brief = TextEditingController();
  int _limit = 10;
  bool _searching = false;
  List<_Cand> _cands = const [];
  Set<String> _picked = {};
  String? _discoverNote;
  String _candPlatform = '';

  // ---- 无限模式 ----
  bool _infinite = false;
  bool _autoFollow = false;
  final _autoBrief = TextEditingController();
  int _autoLimit = 3;
  int _autoInterval = 60;
  int _autoRounds = 0;

  @override
  void dispose() {
    _targets.dispose();
    _message.dispose();
    _brief.dispose();
    _autoBrief.dispose();
    super.dispose();
  }

  Widget _infiniteBar() {
    final state = widget.state;
    final running = state.autoRunning;
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 9, 14, 10),
      decoration: BoxDecoration(
        color: _infinite
            ? AppColors.warn.withValues(alpha: 0.07)
            : Colors.transparent,
        border: const Border(bottom: BorderSide(color: AppColors.borderSoft)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              SizedBox(
                width: 24,
                height: 24,
                child: Checkbox(
                  value: _infinite,
                  onChanged: running
                      ? null
                      : (v) => setState(() {
                          _infinite = v ?? false;
                          if (_infinite) {
                            _autoBrief.text = _brief.text;
                            state.setAction('send_message');
                          }
                        }),
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  visualDensity: VisualDensity.compact,
                  activeColor: AppColors.warn,
                ),
              ),
              const SizedBox(width: 4),
              const Text(
                '无限模式',
                style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
              ),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  '自动循环「找目标 → 发消息」，只填方向与文案',
                  style: TextStyle(fontSize: 10.5, color: AppColors.muted),
                ),
              ),
            ],
          ),
          if (_infinite) ...[
            const SizedBox(height: 8),
            TextField(
              controller: _autoBrief,
              maxLines: 2,
              enabled: !running,
              onChanged: (_) => setState(() {}),
              style: const TextStyle(fontSize: 11.5, height: 1.6),
              decoration: const InputDecoration(
                hintText: '要找什么样的人，例如：在做效率工具、独立开发的博主',
                hintStyle: TextStyle(fontSize: 11.5, color: Color(0xFF4D5666)),
              ),
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                _miniPicker(
                  '每轮',
                  const [3, 5, 10],
                  _autoLimit,
                  running ? null : (v) => setState(() => _autoLimit = v),
                  '个',
                ),
                const SizedBox(width: 8),
                _miniPicker(
                  '间隔',
                  const [30, 60, 120, 300],
                  _autoInterval,
                  running ? null : (v) => setState(() => _autoInterval = v),
                  '秒',
                ),
                const SizedBox(width: 8),
                _miniPicker(
                  '轮数',
                  const [0, 5, 20, 50],
                  _autoRounds,
                  running ? null : (v) => setState(() => _autoRounds = v),
                  _autoRounds == 0 ? '不限' : '轮',
                ),
                const SizedBox(width: 8),
                SizedBox(
                  width: 20,
                  height: 20,
                  child: Checkbox(
                    value: _autoFollow,
                    onChanged: running
                        ? null
                        : (v) => setState(() => _autoFollow = v ?? false),
                    materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    visualDensity: VisualDensity.compact,
                    activeColor: AppColors.warn,
                  ),
                ),
                const Text(
                  '同时关注',
                  style: TextStyle(fontSize: 10.5, color: AppColors.textDim),
                ),
              ],
            ),
            if (_autoStatusCard() != null) ...[
              const SizedBox(height: 8),
              _autoStatusCard()!,
            ],
          ],
        ],
      ),
    );
  }

  Widget _miniPicker(
    String label,
    List<int> values,
    int current,
    ValueChanged<int>? onChanged,
    String unit,
  ) {
    final safe = values.contains(current) ? current : values.first;
    return Container(
      height: 28,
      padding: const EdgeInsets.symmetric(horizontal: 7),
      decoration: BoxDecoration(
        color: const Color(0xFF0B0E13),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          Text(
            '$label ',
            style: const TextStyle(fontSize: 10.5, color: AppColors.muted),
          ),
          DropdownButtonHideUnderline(
            child: DropdownButton<int>(
              value: safe,
              isDense: true,
              dropdownColor: AppColors.panel3,
              style: const TextStyle(fontSize: 11, color: AppColors.text),
              items: values
                  .map(
                    (v) => DropdownMenuItem<int>(
                      value: v,
                      child: Text(
                        v == 0 ? unit : '$v $unit',
                        style: const TextStyle(fontSize: 11),
                      ),
                    ),
                  )
                  .toList(),
              onChanged: onChanged == null ? null : (v) => onChanged(v ?? safe),
            ),
          ),
        ],
      ),
    );
  }

  Widget? _autoStatusCard() {
    final ap = widget.state.autopilot;
    if (ap == null) return null;
    final running = ap['running'] == true;
    final round = ap['round'] ?? 0;
    final stopReason = (ap['stop_reason'] ?? '').toString();
    if (!running && round == 0 && stopReason.isEmpty) return null;

    final phase = (ap['phase'] ?? '').toString();
    final detail = (ap['detail'] ?? '').toString();
    final remain = (ap['remain'] ?? 0) as int;
    final recent = ((ap['recent'] as List?) ?? const [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: running
            ? AppColors.warn.withValues(alpha: 0.08)
            : const Color(0xFF0D1016),
        borderRadius: BorderRadius.circular(7),
        border: Border.all(
          color: running
              ? AppColors.warn.withValues(alpha: 0.4)
              : AppColors.borderSoft,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                running ? Icons.autorenew : Icons.pause_circle_outline,
                size: 13,
                color: running ? AppColors.warn : AppColors.muted,
              ),
              const SizedBox(width: 5),
              Text(
                running
                    ? '第 $round 轮 · 已发 ${ap['sent']} · 失败 ${ap['failed']}'
                    : '上次运行 · 已发 ${ap['sent']} · 失败 ${ap['failed']}',
                style: TextStyle(
                  fontSize: 11,
                  color: running ? const Color(0xFFF0BB6B) : AppColors.textDim,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              if (running && remain > 0)
                Text(
                  '$remain 秒后继续',
                  style: const TextStyle(fontSize: 10, color: AppColors.muted),
                ),
            ],
          ),
          if (phase.isNotEmpty || detail.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Text(
                [
                  if (phase.isNotEmpty) phase,
                  if (detail.isNotEmpty) detail,
                ].join(' · '),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 10.5,
                  color: AppColors.muted,
                  height: 1.4,
                ),
              ),
            ),
          if (running)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                ap['stalled'] == true
                    ? '⚠ 已 ${ap['idle_seconds']} 秒没有进展，可能卡住了'
                    : '心跳：${ap['idle_seconds']} 秒前更新',
                style: TextStyle(
                  fontSize: 9.5,
                  color: ap['stalled'] == true
                      ? AppColors.danger
                      : AppColors.muted,
                ),
              ),
            ),
          if (!running && stopReason.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Text(
                '停止原因：$stopReason',
                style: const TextStyle(fontSize: 10.5, color: AppColors.muted),
              ),
            ),
          if (recent.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: recent
                    .take(3)
                    .map(
                      (r) => Text(
                        '${r['ts']}  ${r['msg']}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 9.5,
                          color: AppColors.muted,
                        ),
                      ),
                    )
                    .toList(),
              ),
            ),
        ],
      ),
    );
  }

  Future<void> _startAuto() async {
    final state = widget.state;
    final p = state.current;
    if (p == null) return;
    if (!p.isDesktop && _autoBrief.text.trim().isEmpty) {
      setState(() => _status = '先写一句要找什么样的人');
      return;
    }
    if (_message.text.trim().isEmpty) {
      setState(() => _status = '无限模式需要先填好文案');
      return;
    }
    final sim = state.simulation;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('启动无限模式？', style: TextStyle(fontSize: 14)),
        content: Text(
          '平台：${p.name}\n'
          '方向：${_autoBrief.text.trim()}\n'
          '每轮最多 $_autoLimit 个目标，间隔 $_autoInterval 秒，'
          '${_autoRounds == 0 ? "不限轮数" : "最多 $_autoRounds 轮"}\n\n'
          '${sim ? "当前是演练模式，不会真实发送。" : "当前是真实执行模式：会给找到的人实际发消息！"}\n'
          '频率上限、去重、急停依然生效。随时可以停止。',
          style: const TextStyle(fontSize: 12, height: 1.7),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: AppColors.warn),
            child: const Text('启动'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;

    setState(() => _status = '正在启动…');
    final err = await state.startAuto(
      brief: _autoBrief.text.trim(),
      message: _message.text,
      interval: _autoInterval,
      limit: _autoLimit,
      maxRounds: _autoRounds,
      autoFollow: _autoFollow,
      targets: _targetList,
    );
    if (!mounted) return;
    setState(() => _status = err ?? '无限模式已启动');
    if (err != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(err),
          backgroundColor: AppColors.danger.withValues(alpha: 0.85),
        ),
      );
    }
  }

  Future<void> _stopAuto() async {
    final err = await widget.state.stopAuto();
    if (!mounted) return;
    setState(() => _status = err ?? '已停止无限模式');
  }

  Widget _actionBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 8, 14, 10),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.borderSoft)),
      ),
      child: _autoButtons(),
    );
  }

  Widget _autoButtons() {
    final running = widget.state.autoRunning;
    return Row(
      children: [
        FilledButton.icon(
          onPressed: running ? _stopAuto : _startAuto,
          icon: Icon(
            running ? Icons.stop_circle_outlined : Icons.all_inclusive,
            size: 16,
          ),
          label: Text(
            running ? '停止无限模式' : '启动无限模式',
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
          ),
          style: FilledButton.styleFrom(
            backgroundColor: running ? AppColors.danger : AppColors.warn,
            foregroundColor: running ? Colors.white : const Color(0xFF1A1206),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            _status ??
                (running
                    ? '正在后台循环执行…'
                    : (widget.state.current?.isDesktop ?? false)
                    ? 'AI 会看界面自己找联系人，不用你指定'
                    : '启动后会持续找新目标，直到你停止或触发上限'),
            style: const TextStyle(fontSize: 11, color: AppColors.muted),
          ),
        ),
      ],
    );
  }

  Widget _targetModeSwitch(PlatformInfo? p) {
    final webOk = p != null && !p.isDesktop;
    return Row(
      children: [
        _modeChip('指定目标', !_byBrief, () => setState(() => _byBrief = false)),
        const SizedBox(width: 6),
        _modeChip('按方向找', _byBrief, () {
          if (!webOk) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('按方向找人只支持网页平台（需要站内搜索）')),
            );
            return;
          }
          setState(() => _byBrief = true);
        }),
        const Spacer(),
        if (_byBrief && _cands.isNotEmpty)
          Text(
            '已选 ${_picked.length}/${_cands.length}',
            style: const TextStyle(fontSize: 10.5, color: AppColors.muted),
          ),
      ],
    );
  }

  Widget _modeChip(String label, bool active, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: active
              ? AppColors.accent.withValues(alpha: 0.14)
              : AppColors.panel2,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(
            color: active
                ? AppColors.accent.withValues(alpha: 0.55)
                : AppColors.border,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 11.5,
            color: active ? const Color(0xFFA8C6FF) : AppColors.textDim,
          ),
        ),
      ),
    );
  }

  Widget _briefBox(PlatformInfo? p) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          controller: _brief,
          maxLines: 3,
          onChanged: (_) => setState(() {}),
          style: const TextStyle(fontSize: 11.5, height: 1.6),
          decoration: const InputDecoration(
            hintText: '用一句话描述你想找谁，例如：找最近在做效率工具、独立开发的博主',
            hintStyle: TextStyle(fontSize: 11.5, color: Color(0xFF4D5666)),
          ),
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            _limitPicker(),
            const SizedBox(width: 8),
            FilledButton.icon(
              onPressed: _searching ? null : _discover,
              icon: _searching
                  ? const SizedBox(
                      width: 12,
                      height: 12,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Color(0xFF06101F),
                      ),
                    )
                  : const Icon(Icons.travel_explore, size: 15),
              label: Text(
                _searching ? '搜索中…' : 'AI 找候选人',
                style: const TextStyle(fontSize: 12),
              ),
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.accent,
                foregroundColor: const Color(0xFF06101F),
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 12,
                ),
              ),
            ),
          ],
        ),
        if (_discoverNote != null)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.info_outline,
                  size: 12,
                  color: AppColors.muted,
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: Text(
                    _discoverNote!,
                    style: const TextStyle(
                      fontSize: 10.5,
                      color: AppColors.muted,
                      height: 1.4,
                    ),
                  ),
                ),
              ],
            ),
          ),
        if (_cands.isNotEmpty) ...[
          const SizedBox(height: 8),
          _candidateList(),
          const SizedBox(height: 4),
          const Text(
            '只把你勾选的人写进目标；陌生人批量私信容易触发风控，请谨慎选择。',
            style: TextStyle(fontSize: 10, color: AppColors.muted, height: 1.4),
          ),
        ],
      ],
    );
  }

  Widget _limitPicker() {
    return Container(
      height: 32,
      padding: const EdgeInsets.symmetric(horizontal: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF0B0E13),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppColors.border),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<int>(
          value: _limit,
          isDense: true,
          dropdownColor: AppColors.panel3,
          style: const TextStyle(fontSize: 11.5, color: AppColors.text),
          items: const [5, 10, 20]
              .map((n) => DropdownMenuItem<int>(value: n, child: Text('$n 个')))
              .toList(),
          onChanged: (v) => setState(() => _limit = v ?? 10),
        ),
      ),
    );
  }

  Widget _candidateList() {
    return Container(
      constraints: const BoxConstraints(maxHeight: 230),
      decoration: BoxDecoration(
        color: const Color(0xFF0D1016),
        borderRadius: BorderRadius.circular(7),
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Flexible(
            child: ListView.builder(
              shrinkWrap: true,
              padding: const EdgeInsets.symmetric(vertical: 4),
              itemCount: _cands.length,
              itemBuilder: (_, i) {
                final c = _cands[i];
                final checked = _picked.contains(c.url);
                return InkWell(
                  onTap: () => setState(() {
                    if (checked) {
                      _picked.remove(c.url);
                    } else {
                      _picked.add(c.url);
                    }
                  }),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 6,
                      vertical: 3,
                    ),
                    child: Row(
                      children: [
                        SizedBox(
                          width: 22,
                          height: 22,
                          child: Checkbox(
                            value: checked,
                            onChanged: (v) => setState(() {
                              if (v == true) {
                                _picked.add(c.url);
                              } else {
                                _picked.remove(c.url);
                              }
                            }),
                            materialTapTargetSize:
                                MaterialTapTargetSize.shrinkWrap,
                            visualDensity: VisualDensity.compact,
                          ),
                        ),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                c.name,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontSize: 11.5),
                              ),
                              Text(
                                c.url,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  fontSize: 9.5,
                                  color: AppColors.muted,
                                ),
                              ),
                            ],
                          ),
                        ),
                        if (c.contacted)
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 4,
                              vertical: 1,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.warn.withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(3),
                            ),
                            child: const Text(
                              '已联系过',
                              style: TextStyle(
                                fontSize: 9,
                                color: Color(0xFFF0BB6B),
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
          const Divider(height: 1, color: AppColors.borderSoft),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
            child: Row(
              children: [
                TextButton(
                  onPressed: () => setState(
                    () => _picked = _cands.map((c) => c.url).toSet(),
                  ),
                  style: TextButton.styleFrom(
                    minimumSize: Size.zero,
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  child: const Text(
                    '全选',
                    style: TextStyle(fontSize: 10.5, color: AppColors.muted),
                  ),
                ),
                TextButton(
                  onPressed: () => setState(() => _picked = {}),
                  style: TextButton.styleFrom(
                    minimumSize: Size.zero,
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  child: const Text(
                    '清空',
                    style: TextStyle(fontSize: 10.5, color: AppColors.muted),
                  ),
                ),
                const Spacer(),
                FilledButton(
                  onPressed: _picked.isEmpty ? null : _applyCandidates,
                  style: FilledButton.styleFrom(
                    backgroundColor: AppColors.accent,
                    foregroundColor: const Color(0xFF06101F),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 10,
                    ),
                  ),
                  child: Text(
                    '加入目标（${_picked.length}）',
                    style: const TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  void _applyCandidates() {
    final existing = _targets.text
        .split(RegExp(r'[\r\n,，]'))
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toSet();
    final add = _picked.where((u) => !existing.contains(u)).toList();
    final merged = [...existing, ...add];
    setState(() {
      _targets.text = merged.join('\n');
      _status = '已加入 ${add.length} 个目标，共 ${merged.length} 个';
    });
  }

  Future<void> _discover() async {
    final p = widget.state.current;
    if (p == null) return;
    if (_brief.text.trim().isEmpty) {
      setState(() => _discoverNote = '先写一句你想找什么样的人');
      return;
    }
    setState(() {
      _searching = true;
      _cands = const [];
      _picked = {};
      _discoverNote = '正在打开搜索页，首次可能需要 10 秒…';
    });
    try {
      final r = await widget.state.discoverTargets(
        p.key,
        _brief.text.trim(),
        _limit,
      );
      if (!mounted) return;
      final list = ((r['candidates'] as List?) ?? const [])
          .map((e) => _Cand.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList();
      setState(() {
        _cands = list;
        _picked = {};
        _candPlatform = p.key;
        final note = (r['note'] ?? '').toString();
        final detail = (r['detail'] ?? '').toString();
        _discoverNote = [
          if (note.isNotEmpty) note,
          if (detail.isNotEmpty) detail,
        ].join(' · ');
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _discoverNote = e.message);
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  List<String> get _targetList => _targets.text
      .split(RegExp(r'[\r\n,，]'))
      .map((e) => e.trim())
      .where((e) => e.isNotEmpty)
      .toSet()
      .toList();

  Future<void> _plan() async {
    setState(() => _status = '正在校验…');
    final err = await widget.state.planNow(
      _targetList,
      _message.text,
      autoFollow: _autoFollow,
    );
    if (!mounted) return;
    setState(
      () => _status = err ?? '已生成 ${widget.state.job?.steps.length ?? 0} 条，待审批',
    );
    if (err != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(err),
          backgroundColor: AppColors.danger.withValues(alpha: 0.85),
        ),
      );
    }
  }

  Future<void> _aiDraft() async {
    final brief = await showDialog<String>(
      context: context,
      builder: (_) => const _BriefDialog(),
    );
    if (brief == null || brief.trim().isEmpty) return;
    setState(() => _status = 'AI 正在生成文案…');
    try {
      final text = await widget.state.draftMessage(brief.trim());
      if (!mounted) return;
      setState(() {
        _message.text = text;
        _status = 'AI 已生成文案，可手动修改';
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _status = null);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.state;
    final p = state.current;
    final counts = state.limitsFor(p?.key ?? '');
    final needMessage =
        state.action == 'send_message' || state.action == 'comment';

    // 换平台后清掉上一个平台的候选，避免把 A 站的人发到 B 站
    if (_candPlatform.isNotEmpty && p != null && p.key != _candPlatform) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        setState(() {
          _cands = const [];
          _picked = {};
          _candPlatform = '';
          _discoverNote = null;
        });
      });
    }

    return Panel(
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _infiniteBar(),
            if (_infinite) _actionBar(),
            _section(
              index: '1',
              title: '动作',
              dim: _infinite,
              trailing: Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                decoration: BoxDecoration(
                  border: Border.all(color: AppColors.border),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  p == null
                      ? '未选平台'
                      : '${p.name} · ${p.isDesktop ? '桌面端' : '网页端'}',
                  style: const TextStyle(
                    fontSize: 10.5,
                    color: AppColors.muted,
                  ),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (p == null)
                    const Text(
                      '请先在左侧选择平台',
                      style: TextStyle(fontSize: 11.5, color: AppColors.muted),
                    )
                  else
                    Wrap(
                      spacing: 6,
                      children: p.actions.map((a) {
                        final active = state.action == a;
                        return GestureDetector(
                          onTap: () => state.setAction(a),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 5,
                            ),
                            decoration: BoxDecoration(
                              color: active
                                  ? AppColors.accent.withValues(alpha: 0.14)
                                  : AppColors.panel2,
                              borderRadius: BorderRadius.circular(7),
                              border: Border.all(
                                color: active
                                    ? AppColors.accent.withValues(alpha: 0.55)
                                    : AppColors.border,
                              ),
                            ),
                            child: Text(
                              p.actionLabels[a] ?? a,
                              style: TextStyle(
                                fontSize: 12,
                                color: active
                                    ? const Color(0xFFA8C6FF)
                                    : AppColors.textDim,
                              ),
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                  if (p != null && p.isDesktop)
                    Padding(
                      padding: const EdgeInsets.only(top: 7),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(
                            Icons.info_outline,
                            size: 13,
                            color: AppColors.warn,
                          ),
                          const SizedBox(width: 5),
                          Expanded(
                            child: Text(
                              '执行前请先把「${p.name}」窗口切到最前面。程序不会自动抢焦点——抢了会让它的弹窗假卡死，之后点哪都没反应。',
                              style: const TextStyle(
                                fontSize: 10.5,
                                color: AppColors.warn,
                                height: 1.5,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  if (p != null && p.hint.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 7),
                      child: Text(
                        p.hint,
                        style: const TextStyle(
                          fontSize: 11,
                          color: AppColors.muted,
                          height: 1.5,
                        ),
                      ),
                    ),
                  if (p != null &&
                      !p.isDesktop &&
                      p.actions.contains('follow') &&
                      state.action == 'send_message')
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Row(
                        children: [
                          SizedBox(
                            width: 22,
                            height: 22,
                            child: Checkbox(
                              value: _autoFollow,
                              onChanged: (v) =>
                                  setState(() => _autoFollow = v ?? false),
                              materialTapTargetSize:
                                  MaterialTapTargetSize.shrinkWrap,
                              visualDensity: VisualDensity.compact,
                              activeColor: AppColors.accent,
                            ),
                          ),
                          const SizedBox(width: 4),
                          const Text(
                            '关注后再发送',
                            style: TextStyle(
                              fontSize: 11.5,
                              color: AppColors.textDim,
                            ),
                          ),
                          const SizedBox(width: 8),
                          const Expanded(
                            child: Text(
                              '先关注对方再发私信；多一次平台操作，间隔会自动放慢',
                              style: TextStyle(
                                fontSize: 10,
                                color: AppColors.muted,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
            _section(
              index: '2',
              title: '目标',
              dim: _infinite && !(widget.state.current?.isDesktop ?? false),
              trailing: Text(
                '${_targetList.length} 个',
                style: const TextStyle(fontSize: 10.5, color: AppColors.muted),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _targetModeSwitch(p),
                  const SizedBox(height: 8),
                  if (!_byBrief) ...[
                    TextField(
                      controller: _targets,
                      maxLines: 5,
                      onChanged: (_) => setState(() {}),
                      style: const TextStyle(
                        fontSize: 11.5,
                        fontFamily: 'Consolas',
                        height: 1.6,
                      ),
                      decoration: InputDecoration(
                        hintText: '每行一个：${p?.targetLabel ?? '链接或账号'}',
                        hintStyle: const TextStyle(
                          fontSize: 11.5,
                          color: Color(0xFF4D5666),
                        ),
                      ),
                    ),
                    const SizedBox(height: 5),
                    Row(
                      children: [
                        const Text(
                          '自动去重；填写顺序就是执行顺序',
                          style: TextStyle(
                            fontSize: 10.5,
                            color: AppColors.muted,
                          ),
                        ),
                        const Spacer(),
                        TextButton(
                          onPressed: () => setState(() => _targets.clear()),
                          style: TextButton.styleFrom(
                            minimumSize: Size.zero,
                            padding: const EdgeInsets.symmetric(horizontal: 4),
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                          child: const Text(
                            '清空',
                            style: TextStyle(
                              fontSize: 10.5,
                              color: AppColors.muted,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ] else
                    _briefBox(p),
                ],
              ),
            ),
            if (needMessage)
              _section(
                index: '3',
                title: '文案',
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    InkWell(
                      onTap: _aiDraft,
                      borderRadius: BorderRadius.circular(5),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 3,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.accent.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(5),
                          border: Border.all(
                            color: AppColors.accent.withValues(alpha: 0.4),
                          ),
                        ),
                        child: const Row(
                          children: [
                            Icon(
                              Icons.auto_awesome,
                              size: 11,
                              color: Color(0xFF9FC0FF),
                            ),
                            SizedBox(width: 4),
                            Text(
                              'AI 生成',
                              style: TextStyle(
                                fontSize: 10.5,
                                color: Color(0xFF9FC0FF),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      '${_message.text.length} 字',
                      style: const TextStyle(
                        fontSize: 10.5,
                        color: AppColors.muted,
                      ),
                    ),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    TextField(
                      controller: _message,
                      maxLines: 4,
                      onChanged: (_) => setState(() {}),
                      style: const TextStyle(fontSize: 12, height: 1.6),
                      decoration: const InputDecoration(
                        hintText: '要发送的内容，可以用 {nick} 自动带上对方昵称',
                        hintStyle: TextStyle(
                          fontSize: 11.5,
                          color: Color(0xFF4D5666),
                        ),
                      ),
                    ),
                    const SizedBox(height: 5),
                    const Text(
                      '支持 {nick}（对方昵称）与 {target}（原始目标）',
                      style: TextStyle(fontSize: 10.5, color: AppColors.muted),
                    ),
                  ],
                ),
              ),
            _section(
              index: needMessage ? '4' : '3',
              title: '安全参数',
              dim: _infinite,
              trailing: const Text(
                '来自 config/settings.json',
                style: TextStyle(fontSize: 10.5, color: AppColors.muted),
              ),
              child: Row(
                children: [
                  _limitBox('${counts['per_hour'] ?? '—'}', '次 / 小时'),
                  const SizedBox(width: 6),
                  _limitBox('${counts['per_day'] ?? '—'}', '次 / 天'),
                  const SizedBox(width: 6),
                  _limitBox(
                    '${counts['delay_min'] ?? '—'}–${counts['delay_max'] ?? '—'}',
                    '秒 / 间隔',
                  ),
                ],
              ),
            ),
            if (!_infinite)
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 6, 14, 14),
                child: Row(
                  children: [
                    FilledButton(
                      onPressed: state.busy ? null : _plan,
                      style: FilledButton.styleFrom(
                        backgroundColor: AppColors.accent,
                        foregroundColor: const Color(0xFF06101F),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 20,
                          vertical: 16,
                        ),
                      ),
                      child: Text(
                        state.busy ? '校验中…' : '生成执行计划',
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    if (_status != null)
                      Expanded(
                        child: Text(
                          _status!,
                          style: const TextStyle(
                            fontSize: 11,
                            color: AppColors.muted,
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

  Widget _limitBox(String value, String label) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        decoration: BoxDecoration(
          color: const Color(0xFF0D1016),
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: AppColors.borderSoft),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              value,
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
            ),
            Text(
              label,
              style: const TextStyle(fontSize: 9.5, color: AppColors.muted),
            ),
          ],
        ),
      ),
    );
  }

  Widget _section({
    required String index,
    required String title,
    Widget? trailing,
    required Widget child,
    bool dim = false,
  }) {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.borderSoft)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SectionHead(title: title, index: index, trailing: trailing),
          const SizedBox(height: 8),
          if (dim)
            Opacity(opacity: 0.38, child: IgnorePointer(child: child))
          else
            child,
        ],
      ),
    );
  }
}

/* ------------------------------------------------------------------ 执行栏 */
class ExecPanel extends StatelessWidget {
  const ExecPanel({super.key, required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final job = state.job;
    final blocked = state.plan.where((p) => !p.allowed).toList();

    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(13, 10, 13, 10),
            child: Row(
              children: [
                const Text(
                  '执行',
                  style: TextStyle(
                    fontSize: 11,
                    letterSpacing: 1.2,
                    color: AppColors.textDim,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const Spacer(),
                Flexible(
                  child: Text(
                    job == null
                        ? '尚未生成计划'
                        : '${job.platformName} · ${job.actionLabel} · ${job.total} 条',
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 11,
                      color: AppColors.muted,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1, color: AppColors.borderSoft),
          if (blocked.isNotEmpty) _blockedBox(context, blocked),
          _actions(context, job),
          _progress(job),
          Expanded(child: _steps(context, job)),
        ],
      ),
    );
  }

  Widget _blockedBox(BuildContext context, List<PlanRow> blocked) {
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 10, 12, 0),
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
      constraints: const BoxConstraints(maxHeight: 120),
      decoration: BoxDecoration(
        color: AppColors.warn.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(7),
        border: Border.all(color: AppColors.warn.withValues(alpha: 0.35)),
      ),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '被安全策略拦截 ${blocked.length} 条',
              style: const TextStyle(
                fontSize: 11,
                color: Color(0xFFF0BB6B),
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 3),
            ...blocked.map(
              (b) => Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text(
                  '· ${b.target} — ${b.reason}',
                  style: const TextStyle(
                    fontSize: 10.5,
                    color: AppColors.textDim,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _actions(BuildContext context, JobInfo? job) {
    final running = job?.status == 'running';
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 6),
      child: Row(
        children: [
          Expanded(
            child: _btn(
              '全部批准',
              AppColors.ok,
              (job?.pending ?? 0) > 0,
              () => _op(context, state.approveAll),
            ),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: _btn(
              '全部拒绝',
              AppColors.warn,
              (job?.pending ?? 0) > 0 || (job?.approved ?? 0) > 0,
              () => _op(context, state.rejectAll),
            ),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: _btn(
              '开始执行',
              AppColors.accent,
              (job?.approved ?? 0) > 0 && !running,
              () => _run(context),
            ),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: _btn(
              '停止',
              AppColors.muted,
              running,
              () => _op(context, state.stopJob),
            ),
          ),
        ],
      ),
    );
  }

  Widget _btn(String label, Color color, bool enabled, VoidCallback onTap) {
    return Opacity(
      opacity: enabled ? 1 : 0.35,
      child: InkWell(
        onTap: enabled ? onTap : null,
        borderRadius: BorderRadius.circular(7),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 7),
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.13),
            borderRadius: BorderRadius.circular(7),
            border: Border.all(color: color.withValues(alpha: 0.45)),
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 11.5,
              color: Color.alphaBlend(
                Colors.white.withValues(alpha: 0.35),
                color,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _progress(JobInfo? job) {
    final p = job?.progress ?? 0;
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
      child: Column(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              value: p,
              minHeight: 5,
              backgroundColor: const Color(0xFF0B0E13),
              valueColor: const AlwaysStoppedAnimation(Color(0xFF4F8CFF)),
            ),
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              Text(
                job == null
                    ? '0 / 0'
                    : '${job.done} / ${job.total}（成功 ${job.ok} · 失败 ${job.failed} · 跳过 ${job.skipped} · 待执行 ${job.approved}）',
                style: const TextStyle(fontSize: 10.5, color: AppColors.muted),
              ),
              const Spacer(),
              Text(
                '${(p * 100).round()}%',
                style: const TextStyle(fontSize: 10.5, color: AppColors.muted),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _steps(BuildContext context, JobInfo? job) {
    if (job == null || job.steps.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            '选择平台并生成计划后，\n这里会列出每一条待执行动作。',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 11.5,
              color: AppColors.muted,
              height: 1.8,
            ),
          ),
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(10, 0, 10, 12),
      itemCount: job.steps.length,
      itemBuilder: (_, i) => _stepRow(context, job.steps[i]),
    );
  }

  Widget _stepRow(BuildContext context, StepInfo s) {
    final statusColor = AppColors.status(s.status);
    return Container(
      margin: const EdgeInsets.only(bottom: 5),
      padding: const EdgeInsets.fromLTRB(8, 7, 8, 7),
      decoration: BoxDecoration(
        color: s.status == 'failed'
            ? AppColors.danger.withValues(alpha: 0.05)
            : AppColors.panel2,
        borderRadius: BorderRadius.circular(7),
        border: Border.all(
          color: s.status == 'failed'
              ? AppColors.danger.withValues(alpha: 0.35)
              : s.status == 'ok'
              ? AppColors.ok.withValues(alpha: 0.28)
              : AppColors.borderSoft,
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 1),
            child: Text(
              '${s.index + 1}'.padLeft(2, '0'),
              style: const TextStyle(
                fontSize: 10,
                color: Color(0xFF4D5666),
                fontFamily: 'Consolas',
              ),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  s.target,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 11.5),
                ),
                if (s.detail.isNotEmpty || s.text.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 1),
                    child: Text(
                      s.detail.isNotEmpty ? s.detail : s.text,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 10.5,
                        color: s.status == 'failed'
                            ? const Color(0xFFFF8A8C)
                            : AppColors.muted,
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 6),
          _chip(
            AppColors.riskLabel(s.risk),
            AppColors.risk(s.risk),
            AppColors.riskBg(s.risk),
          ),
          const SizedBox(width: 4),
          _chip(
            AppColors.statusLabel(s.status),
            statusColor,
            statusColor.withValues(alpha: 0.14),
          ),
          if (s.status == 'pending') ...[
            const SizedBox(width: 4),
            _tinyBtn('批', () => _op(context, () => state.approveStep(s.id))),
            const SizedBox(width: 2),
            _tinyBtn('拒', () => _op(context, () => state.rejectStep(s.id))),
          ],
        ],
      ),
    );
  }

  Widget _chip(String text, Color fg, Color bg) {
    return Container(
      constraints: const BoxConstraints(minWidth: 26),
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(text, style: TextStyle(fontSize: 10, color: fg, height: 1.2)),
    );
  }

  Widget _tinyBtn(String label, VoidCallback onTap) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(4),
      child: Container(
        width: 20,
        height: 18,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: const Color(0xFF0D1016),
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: AppColors.border),
        ),
        child: Text(
          label,
          style: const TextStyle(fontSize: 9.5, color: AppColors.textDim),
        ),
      ),
    );
  }

  Future<void> _op(BuildContext context, Future<String?> Function() fn) async {
    final err = await fn();
    if (err != null && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err)));
    }
  }

  Future<void> _run(BuildContext context) async {
    final sim = state.simulation;
    final job = state.job;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('开始执行', style: TextStyle(fontSize: 14)),
        content: Text(
          sim
              ? '当前是【演练模式】，不会真的操作微信/浏览器。\n\n继续？'
              : '将真实操作 ${job?.platformName ?? ''} · ${job?.actionLabel ?? ''}，共 ${job?.approved ?? 0} 条。\n\n确定开始？',
          style: const TextStyle(fontSize: 12.5, height: 1.7),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('开始'),
          ),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    final err = await state.runJob();
    if (err != null && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err)));
    }
  }
}

/* ------------------------------------------------------------------ 日志栏 */
class LogBar extends StatefulWidget {
  const LogBar({super.key, required this.state});
  final AppState state;

  @override
  State<LogBar> createState() => _LogBarState();
}

class _LogBarState extends State<LogBar> {
  final _scroll = ScrollController();

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _toBottom() {
    if (!_scroll.hasClients) return;
    final atBottom =
        _scroll.position.maxScrollExtent - _scroll.position.pixels < 60;
    if (atBottom) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.jumpTo(_scroll.position.maxScrollExtent);
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final logs = widget.state.logs;
    _toBottom();
    return Container(
      height: 150,
      decoration: const BoxDecoration(
        color: Color(0xFF0B0E13),
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 5, 10, 5),
            child: Row(
              children: [
                const Text(
                  '实时日志',
                  style: TextStyle(
                    fontSize: 11,
                    letterSpacing: 1.2,
                    color: AppColors.muted,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(width: 14),
                Text(
                  '条目 ${logs.length}',
                  style: const TextStyle(
                    fontSize: 10.5,
                    color: AppColors.muted,
                  ),
                ),
                const Spacer(),
                TextButton(
                  onPressed: widget.state.clearLogs,
                  style: TextButton.styleFrom(
                    minimumSize: Size.zero,
                    padding: const EdgeInsets.symmetric(horizontal: 6),
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  child: const Text(
                    '清屏',
                    style: TextStyle(fontSize: 10.5, color: AppColors.muted),
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1, color: AppColors.borderSoft),
          Expanded(
            child: logs.isEmpty
                ? const Center(
                    child: Text(
                      '暂无日志',
                      style: TextStyle(fontSize: 11, color: AppColors.muted),
                    ),
                  )
                : ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.fromLTRB(14, 4, 12, 6),
                    itemCount: logs.length,
                    itemBuilder: (_, i) {
                      final e = logs[i];
                      final color = switch (e.level) {
                        'error' => const Color(0xFFFF8A8C),
                        'warn' => const Color(0xFFF0BB6B),
                        _ => AppColors.textDim,
                      };
                      final time = e.ts.length >= 19
                          ? e.ts.substring(11, 19)
                          : e.ts;
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 1),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              time,
                              style: const TextStyle(
                                fontSize: 10.5,
                                fontFamily: 'Consolas',
                                color: Color(0xFF5B6579),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                e.message,
                                style: TextStyle(
                                  fontSize: 10.5,
                                  color: color,
                                  height: 1.55,
                                ),
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

/* ------------------------------------------------------------------ 意图输入 */
class _BriefDialog extends StatefulWidget {
  const _BriefDialog();

  @override
  State<_BriefDialog> createState() => _BriefDialogState();
}

class _BriefDialogState extends State<_BriefDialog> {
  final _ctrl = TextEditingController();

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Row(
        children: [
          Icon(Icons.auto_awesome, size: 17, color: AppColors.accent),
          SizedBox(width: 8),
          Text('AI 生成文案', style: TextStyle(fontSize: 14)),
        ],
      ),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '用一句话说明你想表达什么，模型会写成可直接发送的消息。',
              style: TextStyle(
                fontSize: 11.5,
                color: AppColors.muted,
                height: 1.6,
              ),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _ctrl,
              autofocus: true,
              maxLines: 3,
              style: const TextStyle(fontSize: 12.5, height: 1.6),
              decoration: const InputDecoration(
                hintText: '例如：约对方下周看一个合作，先自我介绍，语气客气但不谄媚',
                hintStyle: TextStyle(fontSize: 11.5, color: Color(0xFF4D5666)),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('取消'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, _ctrl.text),
          style: FilledButton.styleFrom(
            backgroundColor: AppColors.accent,
            foregroundColor: const Color(0xFF06101F),
          ),
          child: const Text('生成'),
        ),
      ],
    );
  }
}

/// 按方向找人的候选对象。
class _Cand {
  _Cand({required this.name, required this.url, required this.contacted});
  final String name;
  final String url;
  final bool contacted;

  factory _Cand.fromJson(Map<String, dynamic> j) => _Cand(
    name: (j['name'] ?? '').toString(),
    url: (j['url'] ?? '').toString(),
    contacted: j['contacted'] == true,
  );
}
