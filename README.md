# Supplier Information Import

## Overview
The Product Information Import module for Odoo enhances the management of product information, particularly for IoT devices and network equipment. It streamlines the process of importing product details from suppliers, managing this information within Odoo, and facilitating the transfer of relevant data to customers.

## Features

### Current Features
- Import product information from supplier-provided Excel or CSV files
- Store detailed product information including serial numbers, MAC addresses, and other IoT-specific details
- Link imported information to existing products or create new products as needed
- Associate imported data with supplier information in the purchase module
- View imported product information directly from the product form

### Planned Features
- Support for multiple supplier file formats
- Customizable mapping of supplier file columns to Odoo fields
- Automated creation and updating of lot/serial numbers
- Generation of customer-specific reports with relevant device information
- Integration with inventory management for real-time stock updates
- API for bulk data retrieval and updates

## Installation
1. Place the `supplier_information_import` folder in your Odoo addons directory.
2. Update your apps list in Odoo.
3. Find "Product Information Import" in the apps list and click "Install".

## Configuration
After installation:
1. Go to Inventory > Configuration > Settings
2. Enable "Lots & Serial Numbers" if not already active
3. Save the configuration

## Usage
1. Navigate to Inventory > Operations > Import Product Info
2. Select the supplier and upload the file containing product information
3. Map the columns in the file to the corresponding fields in Odoo
4. Process the import
5. View and manage imported information from the product form or dedicated menus

## Development
This module is actively under development. Contributions, suggestions, and feedback are welcome. Please refer to the GitHub repository for the latest updates and to report any issues.

## Dependencies
- base
- product
- purchase
- stock

## Author
[Lasse Larsson, Kubang AB](https://kubang.eu/)

## License
[LGPL-3](https://www.gnu.org/licenses/lgpl-3.0.en.html)

## Support
For support, please add an issue in the GitHub repository.