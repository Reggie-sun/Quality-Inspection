# AI-Native Automation Status

**Status:** `disabled / not installed`

本目录只声明 activation boundary。它不是 runtime、harness、evaluation、promotion、scheduler 或 release system 已启用的证据。

## Current State

- 没有 executable runner 或 CLI。
- 没有 runtime config、ledger 或 scheduler。
- 没有 trusted component registry。
- 没有 schemas 的实际 consumer。
- 没有 train/holdout evaluation engine。
- 没有 focused tests 或 smoke command。

因此，coding agent 不得声称 AI-native automation 已运行、已验证或已保护本仓库，也不得执行猜测出来的命令。

## Forbidden Partial Installation

没有 runner 和 tests 时，禁止只加入看似可执行的 config、schemas、eval cases、registry 或 report 目录。半套文件会制造虚假的安全和验证信号。

## Activation Gate

未来启用必须先通过独立 spec 和 implementation plan，并在同一交付中具备：

1. 目标仓可执行 runner 和明确 CLI entry。
2. 基于目标仓真实路径的 runtime config 和 protected paths。
3. runner 实际消费的完整 schemas。
4. train 与 evaluator-only holdout cases。
5. 从目标仓真实 entry points 生成的 component registry。
6. ledger、report 和 cleanup lifecycle。
7. deterministic hard gates、risk levels、rollback 和 stop conditions。
8. focused tests、negative tests 和至少一次真实 smoke receipt。

component registry 必须生成，禁止从其他仓库复制 inventory。activation 前，本目录应继续只包含本 README。
