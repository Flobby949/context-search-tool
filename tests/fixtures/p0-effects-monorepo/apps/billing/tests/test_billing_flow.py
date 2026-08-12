from apps.billing.src.billing_flow import BillingController


def test_create_invoice() -> None:
    assert BillingController().create_invoice() == "billing invoice accepted"
