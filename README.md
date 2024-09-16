# Supplier Information Import

## Overview
The Supplier Information Import module for Odoo 16 enhances the management of product information, particularly for IoT devices and network equipment. It streamlines the process of importing product details from suppliers, managing this information within Odoo, and facilitating the transfer of relevant data to customers.

## Features

- Import product information from supplier-provided Excel or CSV files
- Store detailed product information including serial numbers, MAC addresses, and other IoT-specific details
- Link imported information to existing products or create new products as needed
- Associate imported data with supplier information in the purchase module
- View imported product information directly from the product form
- Flexible configuration of import formats for different suppliers
- Advanced file analysis for creating combination rules
- Automatic matching of imported data with existing products using combination rules
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
4. Set up combination rules for automatic product matching

## Usage

### Analyzing Import Files
1. Navigate to Inventory > Product Info Import > Analyze Import File
2. Select the import configuration and upload the file
3. Choose the second analysis field (Model No. is automatically set as the first field)
4. Click "Analyze" to process the file and view potential new combination rules
5. Optionally, create new combination rules based on the analysis results

### Importing Product Information
1. Navigate to Inventory > Product Info Import > Import Product Info
2. Select the import configuration and upload the file
3. Click "Import" to process the file

### Viewing Imported Product Information
1. Go to Inventory > Product Info Import > Incoming Product Info
2. Here you can view and manage all imported product information

### Managing Combination Rules
1. Go to Inventory > Product Info Import > All Combination Rules
2. View, edit, or create new combination rules for automatic product matching

### Sending Product Information for Sales Orders and Deliveries
1. Open a confirmed sales order or completed delivery
2. Click the "Send Product Info" button
3. An email composition view will open with the generated Excel report attached
4. Edit the email message if needed and send

## Technical Details
- The module uses a mixin class (`ProductInfoReportMixin`) to handle common functionality for generating and sending Excel reports
- File analysis and combination rule creation are handled by the `FileAnalysisWizard`
- Excel reports are generated using the `xlsxwriter` library
- Email templates are used to prepare the content of email messages for Excel reports
- Chunk-based processing is implemented for efficient handling of large data sets

## Dependencies
- base
- product
- stock
- purchase
- sale
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