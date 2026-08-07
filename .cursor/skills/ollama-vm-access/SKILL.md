---
name: ollama-vm-access
description: Connects to a remote VM that hosts Ollama and runs verification commands over SSH. Use when the user asks to access the Ollama VM, run commands on 192.168.221.32 as ig1, check Ollama availability, or troubleshoot remote model serving. Includes a brief llmfit description for when fine-tuning workflow context is needed.
---

# Ollama VM Access

## Purpose

Connect to the remote Ollama host and execute commands there:

- Host: `192.168.221.32`
- User: `ig1`
- SSH command: `ssh ig1@192.168.221.32`

## Connection workflow

1. Connect with SSH:

```bash
ssh ig1@192.168.221.32
```

2. If password login fails and key auth is expected, use explicit key:

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 ig1@192.168.221.32
```

3. After login, run only remote-side commands in that SSH session.

## Minimal Ollama checks (remote VM)

Use these checks to confirm the service is reachable:

```bash
ollama --version
ollama list
```

If needed, verify service state:

```bash
systemctl status ollama --no-pager
```

## llmfit (brief)

`llmfit` is used for LLM fitting/fine-tuning style workflows. Use it when the user asks to adapt a base model to task-specific data, evaluate fit quality, or discuss a tuning pipeline around locally served models (including Ollama-hosted flows).

## Reporting expectations

When done, report:

- Whether SSH connection succeeded.
- Which remote commands were executed.
- Key outputs/errors relevant to Ollama or llmfit context.
