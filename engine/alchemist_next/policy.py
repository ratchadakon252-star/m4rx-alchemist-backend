from decimal import Decimal
from .schemas import Typed, D, digest


class RiskPolicy(Typed):
    version: str = 'P2_PROVISIONAL_1'
    rr1_min: D = Decimal('1.40')
    rr2_min: D = Decimal('2.50')
    point_size: D = Decimal('0.01')
    preferred_stop_min: D = Decimal('270')
    preferred_stop_max: D = Decimal('355')
    preferred_tp1: D = Decimal('500')
    preferred_tp2: D = Decimal('1000')
    status: str = 'PROVISIONAL_P1_POLICY_NOT_BROKER_APPROVED'

    @property
    def hash(self):
        return digest(self)


POLICY = RiskPolicy()
