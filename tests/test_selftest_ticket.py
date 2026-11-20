"""failure-ticket 自检用：故意失败，验证 CI 失败工单自动创建。验证后立即删除。"""


def test_selftest_deliberate_failure() -> None:
    assert False, "failure-ticket 自检：预期失败，用于验证自动工单链路"
