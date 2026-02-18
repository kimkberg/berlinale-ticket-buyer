# Berlinale Ticket Buyer - Enhanced Fork

> This is a fork from [Rswcf/berlinale-ticket-buyer](https://github.com/Rswcf/berlinale-ticket-buyer)

This fork includes several enhancements and improvements to the original Berlinale ticket automation tool, focused on increasing reliability, precision, and user experience.

## Enhancements Made

### Timing and Precision Improvements
- **Atomic Clock Synchronization**: Added NTP and HTTP fallback time synchronization for sub-second precision in ticket sale timing
- **Refined Browser Automation Timing**: Updated timing configurations with more realistic human-like delays to avoid detection
- **Improved Performance**: Optimized timing parameters for better speed and reliability

### Browser Session Management
- **Persistent Browser Sessions**: Browser sessions now persist across frontend reloads without requiring re-login
- **Session Status Optimization**: Eliminated unnecessary browser reloads during session status checks
- **Crash Recovery**: Enhanced browser context crash recovery mechanisms in BrowserManager

### Configuration Improvements
- **Centralized Ticket Count**: Default ticket count configuration is now centralized and synced via API
- **Festival Date Configuration**: Moved festival dates to configuration file for easier management
- **Debug Mode**: Added debug mode with simulation capabilities for testing

### User Interface Fixes
- **Date Tab Timezone Bug**: Fixed timezone handling issues in date tab navigation
- **Browser Reload Prevention**: Resolved issues with unwanted browser reloads

### Code Quality
- **Improved Error Handling**: Better exception handling in background tasks
- **Enhanced Security**: Improved domain extraction security and validation
- **Code Refactoring**: Simplified logic, extracted helper functions, and reduced code duplication
- **Better Type Safety**: Added proper type hints throughout the codebase

## Getting Started

For installation and usage instructions, please refer to the [original repository](https://github.com/Rswcf/berlinale-ticket-buyer).

## License

[MIT](LICENSE)