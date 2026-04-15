# Commit Template

Steps:

1. Identify the main change.
2. Choose the correct type.
3. Choose the dominant scope.
4. Write a short English title.
5. Add 2 to 4 objective bullets.
6. Finish with the required signature.

Template:

```text
<type>(<scope>): <short summary>

- <change 1>
- <change 2>
- <change 3>

Authored By Codex (GPT 5.4)
```

Examples:

```text
feat(Auth): add frontend login session flow

- create auth context for token and user state
- connect login page to backend auth service
- protect conversations route after sign-in

Authored By Codex (GPT 5.4)
```

```text
fix(Handler): standardize Lambda dependency imports

- move handlers to functions/lambda
- update dependency module paths
- keep entrypoints aligned with backend layout

Authored By Codex (GPT 5.4)
```

```text
refactor(Dao): isolate DynamoDB implementations

- move concrete daos under backend layer structure
- keep business logic bound to interfaces
- remove old persistence paths

Authored By Codex (GPT 5.4)
```

```text
test(Unit): add message flow coverage

- mock queue publisher and websocket notifier
- validate ack authorization behavior
- keep controller request tests isolated

Authored By Codex (GPT 5.4)
```
