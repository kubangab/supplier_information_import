from odoo import _
from odoo.exceptions import UserError

def log_and_notify(env, message, error_type="error"):
    env.user.notify_warning(message=message, title=_("Import Warning"))
    if error_type == "error":
        raise UserError(message)
    elif error_type == "warning":
        env.logger.warning(message)

def collect_errors(errors):
    error_messages = []
    for index, row, error in errors:
        error_messages.append(_(f"Error at row {index}: {error}\nRow data: {row}"))
    return "\n\n".join(error_messages)