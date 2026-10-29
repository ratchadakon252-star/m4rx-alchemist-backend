"""Legacy F aliases are explanatory exports, not decision gates."""

def legacy_f(reason):
    if 'UNSUPPORTED_SYMBOL_PROFILE' in reason or 'STRUCTURAL_RISK_FAIL' in reason or 'SWING_ANCHOR_MISMATCH' in reason or 'BINDING' in reason:
        return 'F4'
    if any(x in reason for x in ('INPUT','QUOTE_UNVERIFIED','SCAN_INCOMPLETE','AFTER_CURSOR','PRICE_PRECISION','SNAPSHOT_MISMATCH')):
        return 'F1'
    if 'EXPIRED' in reason:return 'F2'
    if 'TRIGGER_ABSENT_F3' in reason:return 'F3'
    if any(x in reason for x in ('TARGET_RR_FAIL','TARGET_OBSTRUCTED','RR_BELOW','TARGET_GEOMETRY')):return 'F5'
    if 'ORDER_UNAVAILABLE' in reason:return 'F8'
    return 'F6'
