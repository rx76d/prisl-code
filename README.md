# Prisl Code
![Version](https://img.shields.io/badge/version-v0.1.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-windows%2C%20macos-default)



A local AI coding assistant for your terminal that runs GGUF models using llama.cpp locally.
It can read, write, and execute code in your projects while running offline in an isolated environment.
>You can run your own server too it will detect it and will connect.

## Installation
Prisl Code is designed to be a one-command setup.
```bash
pip install git+https://github.com/rx76d/prisl-code.git
```

## Usage

Once installed, navigate to any folder on your computer and start the assistant by typing:

```bash
prisl-code
```

On its first run, it quietly sets up an isolated environment, installs dependencies (openai, rich, prompt_toolkit, psutil), checks for a local LLM server (ports 8080/11434), and if none is found, offers to auto-download llama-server and opens a native file picker to select a GGUF model.

## Basics
**Add context:**
- Type @filename.py anywhere in your message to instantly inject that file's contents into the AI's memory.

**Commands:**

 - **@\<filepath\>:** Inject a file's content directly into context.
- **/compact:** Clear conversation history to save tokens (keeps system prompt).
- **/history:** Print a summary of the current conversation history.
- **/save:** Export the current chat history to a Markdown file.
- **/clear:** Clear the terminal screen.
- **/help:** Show this help menu.
- **/exit:** Exit the application.

## Requirements
- Python 3.8+
- Pip 23.0+
- Git

## Uninstall

```bash
prisl-code --uninstall
```
> It will remove prisl-code completely, along with its isolated environments, cache and it PATH.

## License

This project is open source and available under the MIT License.

<br>

<div align="center">
<sub>Developed by rx76d</sub>
</div>
