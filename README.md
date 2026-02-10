# Yandex Disk Sync Pro

Professional cloud synchronization solution with advanced features for secure and efficient file synchronization with Yandex.Disk.

## Features

- **System Tray Integration**: Minimize to system tray and continue synchronization in the background
- **Advanced Analytics**: View sync statistics and history with graphical representations
- **Secure API Management**: Encrypted storage of OAuth tokens using Fernet encryption
- **Automatic Startup**: Option to start synchronization automatically on system boot
- **File Monitoring**: Real-time monitoring of local folders for changes
- **Multi-folder Synchronization**: Support for synchronizing multiple folder pairs simultaneously
- **Dark/Light Themes**: Modern UI with customizable themes
- **History Tracking**: Detailed logs of all synchronization operations

## Requirements

- Python 3.8+
- Windows, macOS, or Linux

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd yandex_sync_pro
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

The application stores configuration in `~/.ydsync_pro/` directory:
- `config.json` - Main configuration with encrypted OAuth token
- `history.db` - Database with synchronization history
- `app.log` - Application log file

## Usage

1. Run the application:
```bash
python main.py
```

2. On first run, you'll be prompted to enter your Yandex OAuth token
3. Configure synchronization folders in the settings dialog
4. Start synchronization using the main interface

### Getting OAuth Token

To get your OAuth token:
1. Go to Yandex Disk Polygon
2. Select "Get OAuth Token"
3. Copy the token from the browser address bar
4. Paste it into the application authorization dialog

### Command Line Options

- `--autostart` or `-a`: Run in background mode (for auto-startup)

## Security

- OAuth tokens are stored encrypted using Fernet (AES 128) encryption
- Encryption keys are generated locally and stored securely
- All sensitive data is kept locally on the device

## Dependencies

The project uses several key libraries:
- `yadisk`: Yandex.Disk API client
- `watchdog`: File system monitoring
- `ttkbootstrap`: Modern UI toolkit
- `pystray`: System tray integration
- `cryptography`: Secure token encryption
- `matplotlib`: Analytics visualization

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

Yandex Disk Sync Pro - Professional Cloud Sync Solution
Version: 2.5