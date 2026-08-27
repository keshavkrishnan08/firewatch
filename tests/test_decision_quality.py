"""Decision-quality: precision / recall of the threat flag vs what actually burned."""
from firewatch.decision.quality import decision_metrics


def test_perfect_flagging():
    m = decision_metrics([True, True, False], [True, True, False])
    assert m["precision"] == 1.0 and m["recall"] == 1.0
    assert m["false_alarms"] == 0 and m["missed"] == 0


def test_false_alarm_costs_precision():
    # flagged 2, only 1 burned -> precision 0.5; the burned one was flagged -> recall 1.0
    m = decision_metrics([True, True], [True, False])
    assert m["precision"] == 0.5 and m["recall"] == 1.0
    assert m["false_alarms"] == 1 and m["flagged"] == 2 and m["burned"] == 1


def test_miss_costs_recall():
    # two burned, only one flagged -> recall 0.5; the flagged one burned -> precision 1.0
    m = decision_metrics([True, False], [True, True])
    assert m["precision"] == 1.0 and m["recall"] == 0.5
    assert m["missed"] == 1 and m["burned"] == 2


def test_no_flags_no_burns_are_none():
    m = decision_metrics([False, False], [False, False])
    assert m["precision"] is None and m["recall"] is None
    assert m["flagged"] == 0 and m["burned"] == 0
