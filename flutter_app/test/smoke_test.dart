import 'package:desktop_console/api.dart';
import 'package:desktop_console/theme.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('任务进度按已完成步骤计算', () {
    final job = JobInfo(
      id: 'job_x',
      platform: 'douyin',
      platformName: '抖音',
      action: 'follow',
      actionLabel: '关注',
      mode: 'confirm',
      status: 'planned',
      message: '',
      total: 10,
      pending: 6,
      approved: 0,
      ok: 3,
      failed: 1,
      rejected: 0,
      skipped: 0,
      steps: const [],
    );
    expect(job.done, 4);
    expect(job.progress, closeTo(0.4, 1e-9));

    final empty = JobInfo(
      id: 'job_y',
      platform: 'qq',
      platformName: 'QQ',
      action: 'add_friend',
      actionLabel: '加好友',
      mode: 'confirm',
      status: 'planned',
      message: '',
      total: 0,
      pending: 0,
      approved: 0,
      ok: 0,
      failed: 0,
      rejected: 0,
      skipped: 0,
      steps: const [],
    );
    expect(empty.progress, 0);
  });

  test('平台信息从后端 JSON 解析', () {
    final p = PlatformInfo.fromJson({
      'key': 'wechat',
      'name': '微信',
      'kind': 'desktop',
      'actions': ['send_message'],
      'action_labels': {'send_message': '发消息'},
      'target_label': '好友备注 / 群名',
      'hint': '需要微信 PC 端已登录',
      'color': '#07C160',
      'health': {'ready': true, 'detail': '已连接'},
    });
    expect(p.key, 'wechat');
    expect(p.actions, ['send_message']);
    expect(p.actionLabels['send_message'], '发消息');
    expect(p.isDesktop, isTrue);
    expect(p.color, 0xFF07C160);
    expect(p.health.ready, isTrue);
  });

  test('步骤状态与风险有可读中文', () {
    expect(AppColors.statusLabel('pending'), '待审批');
    expect(AppColors.statusLabel('ok'), '成功');
    expect(AppColors.riskLabel('high'), '高');
    expect(AppColors.risk('high'), AppColors.danger);
  });

  test('日志与计划行解析', () {
    final row = PlanRow.fromJson({
      'target': 'https://www.douyin.com/user/x',
      'risk': 'high',
      'allowed': false,
      'reason': '域名不属于 douyin',
    });
    expect(row.allowed, isFalse);
    expect(row.reason, contains('douyin'));
  });
}
