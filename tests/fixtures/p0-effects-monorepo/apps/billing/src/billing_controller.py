from .service.billing_service import BillingService


class BillingController:
    def create_invoice(self) -> str:
        return BillingService().create_invoice()
