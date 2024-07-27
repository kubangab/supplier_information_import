# Supplier Information Import

## Overview
The Supplier Information Import module for Odoo enhances the management of product information, particularly for IoT devices and network equipment. It streamlines the process of importing product details from suppliers, managing this information within Odoo, and facilitating the transfer of relevant data to customers.

## Features

- Import product information from supplier-provided Excel or CSV files
- Store detailed product information including serial numbers, MAC addresses, and other IoT-specific details
- Link imported information to existing products or create new products as needed
- Associate imported data with supplier information in the purchase module
- View imported product information directly from the product form
- Flexible configuration of import formats for different suppliers
- Automatic matching of imported data with existing products
- Integration with inventory and purchase modules
- Automatic generation of Excel reports with product information for sales orders and deliveries
- Ability to send generated Excel reports via email directly from sales orders and deliveries
- Custom email templates for sending product information reports

## Installation
1. Place the `supplier_information_import` folder in your Odoo addons directory.
2. Update your apps list in Odoo.
3. Find "Supplier Information Import" in the apps list and click "Install".

## Configuration
1. Go to Inventory > Configuration > Product Info Import > Import Configurations
2. Create a new import configuration for each supplier and file format you want to support
3. Define column mappings for each import configuration

## Usage

### Importing Product Information
1. Navigate to Inventory > Product Info Import > Import Product Info
2. Select the import configuration and upload the file
3. Click "Import" to process the file

### Viewing Imported Product Information
1. Go to Inventory > Product Info Import > Incoming Product Info
2. Here you can view and manage all imported product information

### Sending Product Information for Sales Orders
1. Open a confirmed sales order
2. Click the "Send Product Info" button
3. An email composition view will open with the generated Excel report attached
4. Edit the email message if needed and send

### Sending Product Information for Deliveries
1. Open a completed delivery
2. Click the "Send Product Info" button
3. An email composition view will open with the generated Excel report attached
4. Edit the email message if needed and send

## Technical Details
- The module uses a mixin class (`ProductInfoReportMixin`) to handle common functionality for generating and sending Excel reports
- Excel reports are generated using the `xlsxwriter` library
- Email templates are used to prepare the content of email messages for Excel reports

## Dependencies
- base
- product
- stock
- purchase
- xlrd (for Excel file import)
- xlsxwriter (for Excel report generation)

## Development
This module is actively under development. Contributions, suggestions, and feedback are welcome. Please refer to the GitHub repository for the latest updates and to report any issues.

## Author
[Lasse Larsson, Kubang AB](https://kubang.eu/)

## License
[LGPL-3](https://www.gnu.org/licenses/lgpl-3.0.en.html)

## Support
For support, please add an issue in the GitHub repository or contact the developers at [contact information].