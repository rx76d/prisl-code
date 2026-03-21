# Prisl Code

A local AI coding assistant for your terminal that runs GGUF models using llama.cpp locally.
It can read, write, and execute code in your projects while running offline in an isolated environment.
>You can run your server too it will detect it and will connect.

## Installation

```bash
pip install git+https://github.com/rx76d/prisl-code.git
```

## Usage

Once installed, navigate to any folder on your computer and start the assistant by typing:

```bash
prisl-code
```

On its first run, it will take a few moments to quietly set up its isolated environment and ensure a local LLM server is ready to go.

## Basics
**Add context:** Type @filename.py anywhere in your message to instantly inject that file's contents into the AI's memory.

**Commands:**

 - **@<filepath>:** = Inject a file's content directly into context.
- **/compact:** Clear conversation history to save tokens (keeps system prompt).
- **/history:** Print a summary of the current conversation history.
- **/save:** Export the current chat history to a Markdown file.
- **/clear:** Clear the terminal screen.
- **/help:** Show this help menu.
- **/exit:** Exit the application.


## License

This project is open source and available under the MIT License.

<br>

<div align="center">
<sub>Developed by rx76d</sub>
</div>
