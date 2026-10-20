# SPDX-License-Identifier: AGPL-3.0-only
# Added to this derivative on 2026-10-21.
def allowed(sender, owner, private):
    return bool(owner) and sender == owner and private

def format_balance(data):
    rows = ['DeepSeek 账户余额', 'API 状态：' + ('可用' if data.get('is_available') else '余额不足')]
    for item in data.get('balance_infos', []):
        rows.append(f"总余额：{item['total_balance']} {item['currency']}\n充值余额：{item['topped_up_balance']}\n赠送余额：{item['granted_balance']}")
    return '\n'.join(rows)
