"""Demand/notice timeline extraction — synthetic Russian Post tracking
report fixtures, deliberately different tracking numbers/dates/companies
from any real case.
"""
from __future__ import annotations

from datetime import date

from app.domains.litigation.notice_timeline import extract_notice_timeline

_HEADER = (
    "Досудебное требование\n"
    "Представитель ООО «Восток Трейд»\n"
    "по доверенности Иванов И.И.\n"
    "12.03.2025\n\n"
    "Отчет сформирован официальным сайтом Почты России 20 марта 2025 в 09:00\n"
    "Отчет об отслеживании отправления с почтовым идентификатором 30012345678901\n"
)


def test_no_tracking_report_present_returns_unknown():
    result = extract_notice_timeline("Досудебное требование направлено 12.03.2025 без приложений.")
    assert result.tracking_report_present is False
    assert result.final_status == "UNKNOWN"
    assert result.tracking_number is None


def test_dispatched_only_report():
    text = _HEADER + "13 марта 2025, 10:00 Принято в отделении связи 190000, Санкт-Петербург\n"
    result = extract_notice_timeline(text)
    assert result.tracking_report_present is True
    assert result.tracking_number == "30012345678901"
    assert result.demand_date == date(2025, 3, 12)
    assert result.final_status == "DISPATCHED"


def test_delivered_report():
    text = (
        _HEADER
        + "13 марта 2025, 10:00 Принято в отделении связи 190000, Санкт-Петербург\n"
        + "15 марта 2025, 14:20 Вручено 220000, Минск\n"
    )
    result = extract_notice_timeline(text)
    assert result.final_status == "DELIVERED"


def test_notice_left_without_actual_delivery_is_not_reported_as_delivered():
    text = (
        _HEADER
        + "14 марта 2025, 09:00 Прибыло в место вручения 220000, Минск\n"
        + "14 марта 2025, 09:30 Вручено извещение 220000, Минск\n"
    )
    result = extract_notice_timeline(text)
    assert result.final_status == "NOTICE_LEFT"


def test_returned_status_survives_later_return_shipment_transit_events():
    """Regression: once RETURNED is recorded, the report keeps logging
    further transit events describing the RETURN shipment itself moving
    back to the sender — those later lines must not overwrite the
    already-established non-delivery outcome.
    """
    text = (
        _HEADER
        + "14 марта 2025, 09:30 Вручено извещение 220000, Минск\n"
        + "25 марта 2025, 00:00 Срок хранения истек. Выслано обратно отправителю 220000, Минск\n"
        + "27 марта 2025, 11:00 Прибыло в сортировочный центр 190000, Санкт-Петербург\n"
        + "28 марта 2025, 15:00 Покинуло сортировочный центр 190000, Санкт-Петербург\n"
    )
    result = extract_notice_timeline(text)
    assert result.final_status == "RETURNED"


def test_tracking_report_present_but_no_recognized_events_is_unknown():
    text = _HEADER + "some unrelated report content with no recognizable status keywords\n"
    result = extract_notice_timeline(text)
    assert result.tracking_report_present is True
    assert result.final_status == "UNKNOWN"
    assert result.events == []
