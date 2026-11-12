import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// 后端返回的业务错误（带中文 detail）。
class ApiException implements Exception {
  ApiException(this.message, [this.status]);
  final String message;
  final int? status;

  @override
  String toString() => message;
}

class PlatformHealth {
  PlatformHealth({required this.ready, required this.detail});
  final bool ready;
  final String detail;

  factory PlatformHealth.fromJson(Map<String, dynamic>? j) => PlatformHealth(
    ready: j?['ready'] == true,
    detail: (j?['detail'] ?? '').toString(),
  );
}

class PlatformInfo {
  PlatformInfo({
    required this.key,
    required this.name,
    required this.kind,
    required this.actions,
    required this.actionLabels,
    required this.targetLabel,
    required this.hint,
    required this.color,
    required this.health,
  });

  final String key;
  final String name;
  final String kind;
  final List<String> actions;
  final Map<String, String> actionLabels;
  final String targetLabel;
  final String hint;
  final int color;
  final PlatformHealth health;

  bool get isDesktop => kind == 'desktop';

  factory PlatformInfo.fromJson(Map<String, dynamic> j) => PlatformInfo(
    key: j['key'] as String,
    name: j['name'] as String,
    kind: (j['kind'] ?? 'web') as String,
    actions: List<String>.from((j['actions'] as List?) ?? const []),
    actionLabels: ((j['action_labels'] as Map?) ?? const {}).map(
      (k, v) => MapEntry(k.toString(), v.toString()),
    ),
    targetLabel: (j['target_label'] ?? '') as String,
    hint: (j['hint'] ?? '') as String,
    color: _parseColor(j['color'] as String?),
    health: PlatformHealth.fromJson(j['health'] as Map<String, dynamic>?),
  );
}

class StepInfo {
  StepInfo({
    required this.id,
    required this.index,
    required this.target,
    required this.text,
    required this.risk,
    required this.reason,
    required this.status,
    required this.detail,
    required this.screenshot,
  });

  final String id;
  final int index;
  final String target;
  final String text;
  final String risk;
  final String reason;
  final String status;
  final String detail;
  final String? screenshot;

  factory StepInfo.fromJson(Map<String, dynamic> j) => StepInfo(
    id: j['id'] as String,
    index: (j['index'] ?? 0) as int,
    target: (j['target'] ?? '') as String,
    text: (j['text'] ?? '') as String,
    risk: (j['risk'] ?? 'low') as String,
    reason: (j['reason'] ?? '') as String,
    status: (j['status'] ?? 'pending') as String,
    detail: (j['detail'] ?? '') as String,
    screenshot: j['screenshot'] as String?,
  );
}

class JobInfo {
  JobInfo({
    required this.id,
    required this.platform,
    required this.platformName,
    required this.action,
    required this.actionLabel,
    required this.mode,
    required this.status,
    required this.message,
    required this.total,
    required this.pending,
    required this.approved,
    required this.ok,
    required this.failed,
    required this.rejected,
    required this.skipped,
    required this.steps,
  });

  final String id;
  final String platform;
  final String platformName;
  final String action;
  final String actionLabel;
  final String mode;
  final String status;
  final String message;
  final int total;
  final int pending;
  final int approved;
  final int ok;
  final int failed;
  final int rejected;
  final int skipped;
  final List<StepInfo> steps;

  int get done => ok + failed + rejected + skipped;
  double get progress => total == 0 ? 0 : done / total;

  factory JobInfo.fromJson(Map<String, dynamic> j) {
    final s = (j['stats'] as Map?) ?? const {};
    return JobInfo(
      id: j['id'] as String,
      platform: (j['platform'] ?? '') as String,
      platformName: (j['platform_name'] ?? '') as String,
      action: (j['action'] ?? '') as String,
      actionLabel: (j['action_label'] ?? '') as String,
      mode: (j['mode'] ?? '') as String,
      status: (j['status'] ?? '') as String,
      message: (j['message'] ?? '') as String,
      total: (s['total'] ?? 0) as int,
      pending: (s['pending'] ?? 0) as int,
      approved: (s['approved'] ?? 0) as int,
      ok: (s['ok'] ?? 0) as int,
      failed: (s['failed'] ?? 0) as int,
      rejected: (s['rejected'] ?? 0) as int,
      skipped: (s['skipped'] ?? 0) as int,
      steps: ((j['steps'] as List?) ?? const [])
          .map((e) => StepInfo.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class PlanRow {
  PlanRow({
    required this.target,
    required this.risk,
    required this.allowed,
    required this.reason,
  });
  final String target;
  final String risk;
  final bool allowed;
  final String reason;

  factory PlanRow.fromJson(Map<String, dynamic> j) => PlanRow(
    target: (j['target'] ?? '') as String,
    risk: (j['risk'] ?? 'low') as String,
    allowed: j['allowed'] == true,
    reason: (j['reason'] ?? '') as String,
  );
}

class LogEntry {
  LogEntry({
    required this.id,
    required this.level,
    required this.message,
    required this.ts,
  });
  final int id;
  final String level;
  final String message;
  final String ts;
}

class HealthInfo {
  HealthInfo({
    required this.mode,
    required this.simulation,
    required this.panic,
    required this.running,
    required this.pending,
    required this.platforms,
  });

  final String mode;
  final bool simulation;
  final bool panic;
  final int running;
  final int pending;
  final List<PlatformInfo> platforms;

  factory HealthInfo.fromJson(Map<String, dynamic> j) => HealthInfo(
    mode: (j['mode'] ?? 'confirm') as String,
    simulation: j['simulation'] == true,
    panic: j['panic'] == true,
    running: (j['running'] ?? 0) as int,
    pending: (j['pending'] ?? 0) as int,
    platforms: ((j['platforms'] as List?) ?? const [])
        .map((e) => PlatformInfo.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

class ProviderPreset {
  ProviderPreset({
    required this.key,
    required this.name,
    required this.baseUrl,
    required this.models,
  });
  final String key;
  final String name;
  final String baseUrl;
  final List<String> models;

  factory ProviderPreset.fromJson(Map<String, dynamic> j) => ProviderPreset(
    key: j['key'] as String,
    name: j['name'] as String,
    baseUrl: (j['base_url'] ?? '') as String,
    models: List<String>.from((j['models'] as List?) ?? const []),
  );
}

class AiSettings {
  AiSettings({
    required this.provider,
    required this.baseUrl,
    required this.model,
    required this.thinking,
    required this.apiKeySet,
    required this.apiKeyTail,
    required this.providers,
  });

  final String provider;
  final String baseUrl;
  final String model;
  final String thinking;
  final bool apiKeySet;
  final String apiKeyTail;
  final List<ProviderPreset> providers;

  factory AiSettings.fromJson(Map<String, dynamic> j) => AiSettings(
    provider: (j['provider'] ?? 'custom') as String,
    baseUrl: (j['base_url'] ?? '') as String,
    model: (j['model'] ?? '') as String,
    thinking: (j['thinking'] ?? 'medium') as String,
    apiKeySet: j['api_key_set'] == true,
    apiKeyTail: (j['api_key_tail'] ?? '') as String,
    providers: ((j['providers'] as List?) ?? const [])
        .map((e) => ProviderPreset.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

int _parseColor(String? hex) {
  if (hex == null || hex.isEmpty) return 0xFF4F8CFF;
  var h = hex.replaceAll('#', '');
  if (h.length == 6) h = 'FF$h';
  return int.tryParse(h, radix: 16) ?? 0xFF4F8CFF;
}

class ApiClient {
  ApiClient({required this.baseUrl});
  final String baseUrl;
  final HttpClient _client = HttpClient()
    ..connectionTimeout = const Duration(seconds: 6);

  Future<dynamic> _send(
    String method,
    String path, [
    Map<String, dynamic>? body,
    Duration? timeout,
  ]) async {
    final uri = Uri.parse('$baseUrl/api$path');
    HttpClientRequest req;
    try {
      req = await _client.openUrl(method, uri);
    } on SocketException {
      throw ApiException('连不上控制台服务（$baseUrl）。请先运行 start.bat 启动后端。');
    }
    req.headers.contentType = ContentType(
      'application',
      'json',
      charset: 'utf-8',
    );
    if (body != null) {
      req.add(utf8.encode(jsonEncode(body)));
    }
    try {
      final resp = await req.close().timeout(
        timeout ?? const Duration(seconds: 40),
      );
      final text = await resp.transform(utf8.decoder).join();
      dynamic data;
      try {
        data = text.isEmpty ? <String, dynamic>{} : jsonDecode(text);
      } on FormatException {
        throw ApiException(
          '返回内容不是 JSON（HTTP ${resp.statusCode}）',
          resp.statusCode,
        );
      }
      if (resp.statusCode >= 400) {
        final detail = (data is Map && data['detail'] != null)
            ? data['detail'].toString()
            : 'HTTP ${resp.statusCode}';
        throw ApiException(detail, resp.statusCode);
      }
      return data;
    } on TimeoutException {
      throw ApiException('请求超时，后端可能正忙');
    } on SocketException {
      throw ApiException('连接被中断，后端可能已退出');
    }
  }

  Future<HealthInfo> health() async => HealthInfo.fromJson(
    await _send('GET', '/health') as Map<String, dynamic>,
  );

  Future<AiSettings> aiSettings() async => AiSettings.fromJson(
    await _send('GET', '/ai/settings') as Map<String, dynamic>,
  );

  Future<AiSettings> saveAiSettings(Map<String, dynamic> patch) async =>
      AiSettings.fromJson(
        await _send('POST', '/ai/settings', patch) as Map<String, dynamic>,
      );

  Future<Map<String, dynamic>> testAi(Map<String, dynamic> cfg) async =>
      await _send('POST', '/ai/test', cfg) as Map<String, dynamic>;

  Future<Map<String, dynamic>> aiModels({
    String? baseUrl,
    String? apiKey,
  }) async =>
      await _send('POST', '/ai/models', {
            if (baseUrl != null) 'base_url': baseUrl,
            if (apiKey != null) 'api_key': apiKey,
          })
          as Map<String, dynamic>;

  Future<Map<String, dynamic>> draft(
    String brief,
    String platform,
    String action,
  ) async =>
      await _send('POST', '/ai/draft', {
            'brief': brief,
            'platform': platform,
            'action': action,
          })
          as Map<String, dynamic>;

  Future<Map<String, dynamic>> settings() async =>
      await _send('GET', '/settings') as Map<String, dynamic>;

  Future<Map<String, dynamic>> patchSettings(
    Map<String, dynamic> patch,
  ) async =>
      await _send('POST', '/settings', {'patch': patch})
          as Map<String, dynamic>;

  Future<Map<String, dynamic>> plan({
    required String platform,
    required String action,
    required List<String> targets,
    required String message,
    bool autoFollow = false,
  }) async =>
      await _send('POST', '/plan', {
            'platform': platform,
            'action': action,
            'targets': targets,
            'message': message,
            'auto_follow': autoFollow,
          })
          as Map<String, dynamic>;

  Future<JobInfo> job(String id) async {
    final j = await _send('GET', '/jobs/$id') as Map<String, dynamic>;
    return JobInfo.fromJson(j['job'] as Map<String, dynamic>);
  }

  /// 最近一个任务（用于启动时恢复现场）。
  Future<JobInfo?> latestJob() async {
    final j = await _send('GET', '/jobs?limit=1') as Map<String, dynamic>;
    final list = (j['jobs'] as List?) ?? const [];
    if (list.isEmpty) return null;
    final first = list.first as Map<String, dynamic>;
    final id = first['id']?.toString();
    if (id == null || id.isEmpty) return null;
    return job(id);
  }

  Future<JobInfo> approve(
    String id, {
    bool all = false,
    List<String>? stepIds,
  }) async {
    final j =
        await _send(
              'POST',
              '/jobs/$id/approve',
              all ? {'all': true} : {'step_ids': stepIds ?? const []},
            )
            as Map<String, dynamic>;
    return JobInfo.fromJson(j['job'] as Map<String, dynamic>);
  }

  Future<JobInfo> reject(
    String id, {
    bool all = false,
    List<String>? stepIds,
  }) async {
    final j =
        await _send(
              'POST',
              '/jobs/$id/reject',
              all ? {'all': true} : {'step_ids': stepIds ?? const []},
            )
            as Map<String, dynamic>;
    return JobInfo.fromJson(j['job'] as Map<String, dynamic>);
  }

  Future<void> run(String id) async {
    await _send('POST', '/jobs/$id/run', const {});
  }

  Future<void> stop(String id) async {
    await _send('POST', '/jobs/$id/stop', const {});
  }

  Future<bool> panic(bool on) async {
    final j = await _send('POST', '/panic', {'on': on}) as Map<String, dynamic>;
    return j['panic'] == true;
  }

  Future<List<LogEntry>> events(int after) async {
    final j =
        await _send('GET', '/events?after=$after&limit=100')
            as Map<String, dynamic>;
    return ((j['events'] as List?) ?? const [])
        .map(
          (e) => LogEntry(
            id: (e as Map)['id'] as int,
            level: (e['level'] ?? 'info').toString(),
            message: (e['message'] ?? '').toString(),
            ts: (e['ts'] ?? '').toString(),
          ),
        )
        .toList();
  }

  Future<Map<String, dynamic>> audit() async =>
      await _send('GET', '/audit?limit=1') as Map<String, dynamic>;

  Future<Map<String, dynamic>> openPlatform(String key) async =>
      await _send('POST', '/adapters/$key/open', const {})
          as Map<String, dynamic>;

  Future<Map<String, dynamic>> probe(String key) async =>
      await _send('POST', '/adapters/$key/probe', const {})
          as Map<String, dynamic>;

  Future<Map<String, dynamic>> setupStatus() async =>
      await _send('GET', '/setup/status') as Map<String, dynamic>;

  Future<Map<String, dynamic>> installChromeMcp({bool force = false}) async =>
      await _send('POST', '/setup/chrome-mcp', {
            'force': force,
          }, const Duration(minutes: 6))
          as Map<String, dynamic>;

  /// 按方向找人：AI 出关键词 → 平台搜索 → 返回候选（只读，不发消息）。
  Future<Map<String, dynamic>> discover(
    String platform,
    String brief,
    int limit,
  ) async =>
      await _send('POST', '/discover', {
            'platform': platform,
            'brief': brief,
            'limit': limit,
          }, const Duration(seconds: 150))
          as Map<String, dynamic>;

  Future<Map<String, dynamic>> autoStatus() async =>
      await _send('GET', '/auto/status') as Map<String, dynamic>;

  Future<Map<String, dynamic>> autoStart(Map<String, dynamic> body) async =>
      await _send('POST', '/auto/start', body, const Duration(seconds: 60))
          as Map<String, dynamic>;

  Future<Map<String, dynamic>> autoStop() async =>
      await _send('POST', '/auto/stop', const {}, const Duration(seconds: 30))
          as Map<String, dynamic>;

  void close() => _client.close(force: true);
}
