import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import 'api.dart';

class AppState extends ChangeNotifier {
  AppState(this.api);

  final ApiClient api;

  HealthInfo? health;
  Map<String, dynamic>? config;
  AiSettings? ai;
  JobInfo? job;
  Map<String, dynamic>? autopilot;
  List<PlanRow> plan = const [];
  final List<LogEntry> logs = [];

  String? connError;
  bool busy = false;

  String platform = 'wechat';
  String action = 'send_message';

  Timer? _timer;
  int _tick = 0;
  int _lastEvent = 0;
  bool _ticking = false;
  bool _disposed = false;

  List<PlatformInfo> get platforms => health?.platforms ?? const [];

  PlatformInfo? get current {
    for (final p in platforms) {
      if (p.key == platform) return p;
    }
    return null;
  }

  bool get panic => health?.panic ?? false;
  bool get simulation =>
      config?['simulation'] == true ||
      (config == null && (health?.simulation ?? true));
  String get mode => (config?['mode'] ?? health?.mode ?? 'confirm').toString();

  /// 当前平台的限流，用于界面展示。
  Map<String, dynamic> limitsFor(String key) {
    final g = (config?['guardrails'] as Map?) ?? const {};
    final def = (g['default'] as Map?) ?? const {};
    final per = ((g['per_platform'] as Map?) ?? const {})[key] as Map?;
    return {
      'per_hour': per?['per_hour'] ?? def['per_hour'],
      'per_day': per?['per_day'] ?? def['per_day'],
      'delay_min': per?['delay_min'] ?? def['delay_min'],
      'delay_max': per?['delay_max'] ?? def['delay_max'],
    };
  }

  Future<void> start() async {
    await refreshAll();
    _timer = Timer.periodic(const Duration(milliseconds: 1600), (_) => tick());
  }

  Future<void> refreshAll() async {
    try {
      config = await api.settings();
      ai = await api.aiSettings();
      health = await api.health();
      connError = null;
      if (platforms.isNotEmpty && !platforms.any((p) => p.key == platform)) {
        platform = platforms.first.key;
        action = platforms.first.actions.first;
      }
      // 启动时恢复最近一个任务，避免刷新/重启后计划丢失
      if (job == null) {
        job = await api.latestJob();
        if (job != null) {
          platform = job!.platform;
          action = job!.action;
        }
      }
    } on ApiException catch (e) {
      connError = e.message;
    }
    _safeNotify();
  }

  Future<void> refreshHealth() async {
    try {
      health = await api.health();
      connError = null;
    } on ApiException catch (e) {
      connError = e.message;
    }
    _safeNotify();
  }

  Future<void> tick() async {
    if (_ticking || _disposed) return;
    _ticking = true;
    _tick++;
    try {
      if (connError != null || _tick % 4 == 1) {
        await refreshHealth();
      }
      if (job != null) {
        final j = await api.job(job!.id);
        job = j;
      }
      autopilot = await api.autoStatus();
      final evs = await api.events(_lastEvent);
      if (evs.isNotEmpty) {
        for (final e in evs) {
          _lastEvent = math.max(_lastEvent, e.id);
          logs.add(e);
        }
        if (logs.length > 400) logs.removeRange(0, logs.length - 400);
      }
    } on ApiException catch (e) {
      connError = e.message;
    } finally {
      _ticking = false;
      _safeNotify();
    }
  }

  void _safeNotify() {
    if (!_disposed) notifyListeners();
  }

  void selectPlatform(String key) {
    platform = key;
    final p = current;
    if (p != null && !p.actions.contains(action)) {
      action = p.actions.first;
    }
    _safeNotify();
  }

  void setAction(String a) {
    action = a;
    _safeNotify();
  }

  /// 生成计划；成功返回 null，失败返回错误文案。
  Future<String?> planNow(
    List<String> targets,
    String message, {
    bool autoFollow = false,
  }) async {
    if (targets.isEmpty) return '请至少填写一个目标';
    if (action == 'send_message' && message.trim().isEmpty) return '发消息需要填写文案';
    busy = true;
    _safeNotify();
    try {
      final res = await api.plan(
        platform: platform,
        action: action,
        targets: targets,
        message: message,
        autoFollow: autoFollow,
      );
      job = JobInfo.fromJson(res['job'] as Map<String, dynamic>);
      plan = ((res['plan'] as List?) ?? const [])
          .map((e) => PlanRow.fromJson(e as Map<String, dynamic>))
          .toList();
      return null;
    } on ApiException catch (e) {
      return e.message;
    } finally {
      busy = false;
      _safeNotify();
    }
  }

  Future<String?> approveAll() => _jobOp(() => api.approve(job!.id, all: true));
  Future<String?> rejectAll() => _jobOp(() => api.reject(job!.id, all: true));

  Future<String?> approveStep(String id) =>
      _jobOp(() => api.approve(job!.id, stepIds: [id]));
  Future<String?> rejectStep(String id) =>
      _jobOp(() => api.reject(job!.id, stepIds: [id]));

  Future<String?> _jobOp(Future<JobInfo> Function() op) async {
    if (job == null) return '还没有任务';
    busy = true;
    _safeNotify();
    try {
      job = await op();
      return null;
    } on ApiException catch (e) {
      return e.message;
    } finally {
      busy = false;
      await refreshHealth();
    }
  }

  Future<String?> runJob() async {
    if (job == null) return '还没有任务';
    try {
      await api.run(job!.id);
      job = await api.job(job!.id);
      await refreshHealth();
      return null;
    } on ApiException catch (e) {
      return e.message;
    }
  }

  Future<String?> stopJob() async {
    if (job == null) return null;
    try {
      await api.stop(job!.id);
      job = await api.job(job!.id);
      return null;
    } on ApiException catch (e) {
      return e.message;
    }
  }

  Future<String?> togglePanic(bool on) async {
    try {
      await api.panic(on);
      await refreshHealth();
      return null;
    } on ApiException catch (e) {
      return e.message;
    }
  }

  Future<String?> setMode(String m) async {
    try {
      config = await api.patchSettings({'mode': m});
      return null;
    } on ApiException catch (e) {
      return e.message;
    } finally {
      _safeNotify();
    }
  }

  Future<String?> setSimulation(bool on) async {
    try {
      config = await api.patchSettings({'simulation': on});
      return null;
    } on ApiException catch (e) {
      return e.message;
    } finally {
      _safeNotify();
    }
  }

  Future<String?> openPlatform(String key) async {
    try {
      final r = await api.openPlatform(key);
      await refreshHealth();
      return r['detail']?.toString();
    } on ApiException catch (e) {
      return e.message;
    }
  }

  Future<Map<String, dynamic>> probePlatform(String key) async {
    try {
      return await api.probe(key);
    } on ApiException catch (e) {
      return {
        'ok': false,
        'data': {'error': e.message},
      };
    }
  }

  Future<String> draftMessage(String brief) async {
    final r = await api.draft(brief, current?.name ?? platform, action);
    if (r['ok'] != true) {
      throw ApiException((r['detail'] ?? '生成失败').toString());
    }
    return (r['text'] ?? '').toString();
  }

  Future<AiSettings> saveAi(Map<String, dynamic> patch) async {
    ai = await api.saveAiSettings(patch);
    _safeNotify();
    return ai!;
  }

  Future<Map<String, dynamic>> testAi(Map<String, dynamic> cfg) =>
      api.testAi(cfg);

  /// 拉取服务商可用模型列表。
  Future<Map<String, dynamic>> fetchModels(String baseUrl, String apiKey) =>
      api.aiModels(baseUrl: baseUrl, apiKey: apiKey);

  Future<Map<String, dynamic>> setupStatus() => api.setupStatus();

  Future<Map<String, dynamic>> installChromeMcp({bool force = false}) =>
      api.installChromeMcp(force: force);

  /// 按方向找人（只读搜索，返回候选给用户勾选）。
  Future<Map<String, dynamic>> discoverTargets(
    String platform,
    String brief,
    int limit,
  ) => api.discover(platform, brief, limit);

  bool get autoRunning => autopilot?['running'] == true;

  Future<String?> startAuto({
    required String brief,
    required String message,
    int interval = 120,
    int limit = 5,
    int maxRounds = 0,
    bool autoFollow = false,
  }) async {
    try {
      autopilot = await api.autoStart({
        'platform': platform,
        'brief': brief,
        'message': message,
        'action': action,
        'interval': interval,
        'limit': limit,
        'max_rounds': maxRounds,
        'auto_follow': autoFollow,
      });
      _safeNotify();
      return null;
    } on ApiException catch (e) {
      return e.message;
    }
  }

  Future<String?> stopAuto() async {
    try {
      autopilot = await api.autoStop();
      _safeNotify();
      return null;
    } on ApiException catch (e) {
      return e.message;
    }
  }

  void clearLogs() {
    logs.clear();
    _safeNotify();
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    api.close();
    super.dispose();
  }
}
