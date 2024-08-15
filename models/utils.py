import base64
import csv
import io
import xlrd
from odoo import _
import logging
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

def process_csv(file_content, chunk_size=1000):
    """
    Process a CSV file and return its contents as a list of dictionaries.

    :param file_content: The content of the CSV file as bytes
    :return: A list of dictionaries, where each dictionary represents a row in the CSV file
    :raises UserError: If there's an error processing the CSV file
    """
    try:
        csv_data = io.StringIO(file_content.decode('utf-8'))
        reader = csv.DictReader(csv_data, delimiter=';')
        
        chunk = []
        for row in reader:
            chunk.append(row)
            if len(chunk) == chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk

    except Exception as e:
        raise UserError(_('Error processing CSV file: %s') % str(e))

def process_excel(file_content, chunk_size=1000):
    """
    Process an Excel file and return its contents as a list of dictionaries.

    :param file_content: The content of the Excel file as bytes
    :return: A list of dictionaries, where each dictionary represents a row in the Excel file
    :raises UserError: If there's an error processing the Excel file
    """
    try:
        workbook = xlrd.open_workbook(file_contents=file_content)
        sheet = workbook.sheet_by_index(0)
        headers = [str(cell.value).strip() for cell in sheet.row(0)]
        
        chunk = []
        for row_index in range(1, sheet.nrows):
            row_data = {}
            for col, header in enumerate(headers):
                cell_value = sheet.cell_value(row_index, col)
                if isinstance(cell_value, float) and cell_value.is_integer():
                    cell_value = int(cell_value)
                row_data[header] = str(cell_value).strip()
            chunk.append(row_data)
            if len(chunk) == chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk

    except Exception as e:
        raise UserError(_('Error processing Excel file: %s') % str(e))

def log_and_notify(env, message, error_type="error"):
    """
    Log a message using Odoo's logging system.

    :param env: The Odoo environment
    :param message: The message to log
    :param error_type: The type of the message ("error", "warning", or "info")
    :raises UserError: If error_type is "error"
    """
    if error_type == "error":
        _logger.error(message)
        raise UserError(message)
    elif error_type == "warning":
        _logger.warning(message)
    else:
        _logger.info(message)

def collect_errors(errors):
    """
    Collect and format error messages.

    :param errors: A list of tuples containing (index, row, error)
    :return: A formatted string containing all error messages
    """
    error_messages = []
    for index, row, error in errors:
        error_messages.append(_("Error at row {}: {}\nRow data: {}").format(index, error, row))
    return "\n\n".join(error_messages)