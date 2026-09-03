# Tool reference

Generated from the server's own tool catalogue by `scripts/gen_tool_docs.py`; do not edit by hand. `tests/test_docs_current.py` fails when this file is out of date.

30 tools.

## `check_for_callbacks`

*read-only*

See if SSRF, XSS, or canary callbacks arrived in the last N minutes.

Use after generate_oob_payloads. For a website verification email, use
wait_for_email.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `since_minutes` | integer |  | `60` |
| `identifier` | string |  |  |

## `configure_webhook`

Create a webhook with custom settings, or update one (pass webhook_token).

Use when the endpoint should pretend to be an API (status, body, content
type, delay up to 30s, CORS), needs an alias, expiry (seconds), a
request_limit (0 stores nothing), listen (seconds to wait for
update_request response), actions on/off, clone_from another token, a
group_id, or a description (label shown in the Control Panel).
default_content can be a JSON array of DNS records
([{"type":"a","value":"..."}]) to answer DNSHook lookups. Updates keep
every setting you do not mention. For a plain sign-up inbox use
create_webhook.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string |  |  |
| `default_status` | integer |  |  |
| `default_content` | string or object or array of any |  |  |
| `default_content_type` | string |  |  |
| `timeout` | integer |  |  |
| `listen` | integer |  |  |
| `cors` | boolean |  |  |
| `alias` | string |  |  |
| `expiry` | integer |  |  |
| `request_limit` | integer |  |  |
| `actions` | boolean |  |  |
| `clone_from` | string |  |  |
| `group_id` | integer |  |  |
| `description` | string |  |  |

## `create_webhook`

Create a disposable inbox to sign up on a website: HTTP URL, temp email, DNS.

Use this first when the user wants to sign up, receive a verification /
magic-link / password-reset email, catch a webhook callback, or get a
one-off URL. Returns token, url, email ({token}@email.webhook.site),
and dns. Next: give the email or URL to the site, then wait_for_email,
then follow_email_link or use the OTP. With an API key the URL is
permanent (premium) unless WEBHOOK_SITE_DEFAULT_EXPIRY is set; use
configure_webhook for custom responses, alias, expiry or request_limit.

## `delete_all_requests`

*destructive, idempotent*

Clear captured events on a webhook, optionally by date or search query.

Use to reset an inbox before a new sign-up or test run. date_to='now-7d'
deletes everything older than a week.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `date_from` | string |  |  |
| `date_to` | string |  |  |
| `query` | string |  |  |

## `delete_request`

*destructive, idempotent*

Delete one captured HTTP, email, or DNS event by request id.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `request_id` | string | yes |  |

## `delete_webhook`

*destructive, idempotent*

Permanently delete a webhook and every captured request/email.

Use when the user is done with a temp inbox or wants to clean up.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |

## `download_request_file`

*read-only*

Download an uploaded file or email attachment (base64) by its file_id.

file_id comes from the attachments list on a request or email.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `request_id` | string | yes |  |
| `file_id` | string | yes |  |
| `max_bytes` | integer |  | `5000000` |

## `export_webhook_data`

*read-only*

Full dump of captured events with HTML and untruncated bodies, as JSON or CSV.

Use when list/wait tools omitted HTML or truncated a body. json pages
through up to limit events; csv returns the account's CSV export
(paid plans, 3 calls per minute). Filters match search_requests.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `format` | `json` | `csv` |  | `json` |
| `limit` | integer |  | `100` |
| `query` | string |  |  |
| `date_from` | string |  |  |
| `date_to` | string |  |  |
| `sorting` | `newest` | `oldest` |  | `newest` |

## `extract_links_from_request`

*read-only*

Pull confirm, reset, magic-link, and other URLs from a captured email or HTTP body.

Use after wait_for_email or get_webhook_requests when the user needs
the verification / login / password-reset link or OTP. Defaults to the
latest event. wait_for_email already extracts links and codes.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `request_id` | string |  |  |
| `filter_domain` | string |  |  |

## `follow_email_link`

Open the verify / magic-link / reset URL from a captured sign-up email.

Use after wait_for_email. Opens the best-ranked auth link; pass
request_id (the email's uuid) to pick a specific email, or url to open
another link from that email. Only follows http(s) links already in the
inbox, to public hosts unless the server's FOLLOW_EMAIL_LINK_ALLOW_HOSTS
allows more. Returns status, final URL, page preview, the ranked
auth_links, and blocked_redirect if a redirect was refused after the
link itself succeeded. For OTP codes, read verification_codes from
wait_for_email.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `request_id` | string |  |  |
| `url` | string |  |  |

## `generate_oob_payloads`

*read-only*

Build authorized out-of-band payloads that ping this webhook: SSRF URLs, XSS callbacks, or canary tokens.

Use only on systems you are allowed to test — not for sign-up email.
kind='ssrf' (include_dns/include_ip), 'xss' (include_cookies/include_dom),
'canary' (canary_type url|dns|email: a tripwire, not an inbox). Confirm
hits with check_for_callbacks.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `kind` | `ssrf` | `xss` | `canary` | yes |  |
| `identifier` | string |  |  |
| `include_dns` | boolean |  | `True` |
| `include_ip` | boolean |  | `True` |
| `include_cookies` | boolean |  | `True` |
| `include_dom` | boolean |  | `True` |
| `canary_type` | `url` | `dns` | `email` |  | `url` |

## `get_request`

*read-only*

Return one captured event: the newest by default, or request_id.

Set raw=true to also get the untouched body (raw_body). Use for a quick
peek; prefer wait_for_email after a sign-up, or get_webhook_requests to
see history.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `request_id` | string |  |  |
| `raw` | boolean |  | `False` |

## `get_webhook_email`

*read-only*

Return the temp inbox to sign up, verify, magic-link, or reset a password.

Address is {token}@email.webhook.site. Use when the user already has a
token. If they do not, call create_webhook first — it also returns
email. After the site sends mail, call wait_for_email.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `validate` | boolean |  | `False` |

## `get_webhook_info`

*read-only*

Show a webhook's settings, expiry, request count and every address.

Returns url, subdomain_url, api_url, email and dns for the token, plus
premium / expires_at / alias / request_limit. Use when the user asks if a
token is still valid, how it is configured, or needs its callback URL or
DNSHook domain.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |

## `get_webhook_requests`

*read-only*

List captured HTTP, email, or DNS events for a webhook, one page at a time.

Use to inspect what already arrived. Bodies are truncated and HTML is
omitted; use export_webhook_data for the full dump. For the newest item
use get_request. To wait for something new use wait_for_request or
wait_for_email. Filter emails with request_type='email'. Returns
pagination (is_last_page, total).

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `limit` | integer |  | `10` |
| `request_type` | `web` | `email` | `dns` |  |  |
| `page` | integer |  | `1` |

## `list_webhooks`

*read-only*

List the webhooks (URLs / inboxes) in the account. Needs WEBHOOK_SITE_API_KEY.

Use to find an existing token, alias, request count or latest_request_at
before creating a new one. Returns pagination.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `page` | integer |  | `1` |
| `per_page` | integer |  | `50` |
| `order_by` | `created_at` | `token_id` |  | `created_at` |
| `order_direction` | `asc` | `desc` |  | `desc` |
| `max_items` | integer |  | `200` |

## `manage_custom_actions`

*destructive*

Manage the Custom Actions webhook.site runs on every request or email a token receives.

action: types (reference of all 63 action types; pass type= for one
type's parameters, live-verified status and example) | variables
($request.*$ variables and modifiers) | list | create | update |
delete | test | execute. create/update take type (modify_response,
http, script, javascript, send_email, extract_jsonpath, condition,
rate_limit, log, set_variable, mock, ...) with parameters, order, and
optionally queue/delay/condition (id of a conditions action) and
queue_id (a Queue Profile from manage_queues to throttle queued runs).
test dry-runs the given action against request_id; execute re-runs all
saved actions on request_id. Actions also fire on incoming emails, so
guard email-sending actions with a condition on $request.type$. Never
point http/send_request at a webhook.site URL (recursion is disabled).

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `action` | `list` | `create` | `update` | `delete` | `test` | `execute` | `types` | `variables` | yes |  |
| `webhook_token` | string |  |  |
| `action_id` | string |  |  |
| `request_id` | string |  |  |
| `type` | string |  |  |
| `parameters` | object |  |  |
| `order` | integer |  |  |
| `disabled` | boolean |  |  |
| `queue` | boolean |  |  |
| `delay` | integer |  |  |
| `condition` | string |  |  |
| `queue_id` | integer |  |  |
| `error_notifications` | boolean |  | `False` |

## `manage_databases`

*destructive*

Manage webhook.site Databases and run SQL against them (needs API key).

action: list | create | update | delete | query. create needs name and
plan. query runs SQL with optional positional (?) or named (:name)
params and returns up to 1000 rows.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `action` | `list` | `create` | `update` | `delete` | `query` | yes |  |
| `database_id` | string |  |  |
| `name` | string |  |  |
| `plan` | `db-s` | `db-m` | `db-l` |  |  |
| `group_id` | integer |  |  |
| `query` | string |  |  |
| `params` | array of any or object |  |  |
| `page` | integer |  | `1` |

## `manage_global_variables`

*destructive*

Manage Global Variables shared by all URLs, usable as $name$ in Custom Actions and Schedules.

action: list | create | update | delete. Needs API key.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `action` | `list` | `create` | `update` | `delete` | yes |  |
| `variable_id` | integer |  |  |
| `name` | string |  |  |
| `value` | string or object or array of any |  |  |
| `search` | string |  |  |
| `page` | integer |  | `1` |

## `manage_groups`

*destructive*

Manage Groups that organise the account's webhooks (needs API key).

action: list | create | update | delete. Assign a token to a group with
configure_webhook(group_id=...).

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `action` | `list` | `create` | `update` | `delete` | yes |  |
| `group_id` | integer |  |  |
| `name` | string |  |  |
| `page` | integer |  | `1` |

## `manage_queues`

*destructive*

Manage Queue Profiles that throttle queued Custom Actions (needs API key).

action: list | create | update | delete. A profile allows `amount` jobs
every `duration` seconds, drops jobs not run within `expiry` seconds,
and waits `delay` seconds before the first run. Attach it to an action
with manage_custom_actions(queue=true, queue_id=...).

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `action` | `list` | `create` | `update` | `delete` | yes |  |
| `queue_id` | integer |  |  |
| `name` | string |  |  |
| `amount` | integer |  |  |
| `duration` | integer |  |  |
| `expiry` | integer |  |  |
| `delay` | integer |  |  |
| `group_id` | integer |  |  |
| `page` | integer |  | `1` |

## `manage_schedules`

*destructive*

Manage Schedules: webhook.site calls request_url on an interval (needs API key).

action: list | get | create | update | delete | run | logs. interval is
monthly, weekly, daily, hourly, 10-minute, 5-minute, 1-minute or cron
(then set cron, e.g. '*/5 * * * *'). request_headers are newline
separated. require_* raise an error notification when the response does
not match. Use for uptime checks or periodic cleanup calls.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `action` | `list` | `get` | `create` | `update` | `delete` | `run` | `logs` | yes |  |
| `schedule_id` | integer |  |  |
| `name` | string |  |  |
| `interval` | string |  |  |
| `cron` | string |  |  |
| `request_url` | string |  |  |
| `request_method` | string |  |  |
| `request_body` | string or object or array of any |  |  |
| `request_headers` | string |  |  |
| `timeout` | integer |  |  |
| `require_body` | string |  |  |
| `require_status_min` | integer |  |  |
| `require_status_max` | integer |  |  |
| `sorting` | `newest` | `oldest` |  | `newest` |
| `page` | integer |  | `1` |

## `manage_templates`

*destructive*

Manage Templates: reusable sets of Custom Actions plus predefined variables (needs API key).

action: list | create | update | delete. actions is a list of action
objects (type, order, parameters...); variables is a list of
{name, value}. Include a template in a token with a 'template' action.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `action` | `list` | `create` | `update` | `delete` | yes |  |
| `template_id` | integer |  |  |
| `name` | string |  |  |
| `actions` | array of object |  |  |
| `variables` | array of object |  |  |
| `page` | integer |  | `1` |

## `manage_users`

*destructive*

Manage team users on an Enterprise account (needs an administrator API key).

action: list | invite | update | delete. user_type_id: 100 admin, 200
member, 300 viewer.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `action` | `list` | `invite` | `update` | `delete` | yes |  |
| `user_id` | integer |  |  |
| `name` | string |  |  |
| `email` | string |  |  |
| `user_type_id` | integer |  |  |
| `role_id` | integer |  |  |
| `page` | integer |  | `1` |

## `search_requests`

*read-only*

Search captured events by method, body text, headers, type, or date.

Use when the user asks to find POSTs, a keyword, or only emails/DNS.
query uses webhook.site search syntax: 'method:POST', 'content:verify',
'headers.user-agent:curl', 'type:web AND method:POST',
'created_at:[now-1h TO now]'. Dates are 'yyyy-MM-dd HH:mm:ss' or
expressions like now-7d. Returns pagination.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `request_type` | `web` | `email` | `dns` |  |  |
| `query` | string |  |  |
| `date_from` | string |  |  |
| `date_to` | string |  |  |
| `sorting` | `newest` | `oldest` |  | `newest` |
| `limit` | integer |  | `20` |
| `page` | integer |  | `1` |

## `send_requests`

Send one JSON body (data) or several (payloads) to the webhook URL to test capture.

Use when the user wants to send sample payloads or load-test, not when
they are waiting for a real site or email. Any HTTP method; delay_ms
spaces out multiple payloads.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `data` | object |  |  |
| `payloads` | array of object |  |  |
| `headers` | object |  |  |
| `method` | string |  | `POST` |
| `delay_ms` | integer |  | `0` |

## `server_status`

*read-only*

Check this server's setup: API key, account reachability, plan, real-time socket, env config.

Call first when a tool fails unexpectedly or before relying on account
features. Lists problems in plain words.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `check_socket` | boolean |  | `True` |

## `update_request`

*idempotent*

Attach a note to a captured request, or set its dynamic response.

response_* call the Set Response API; it only reaches the caller when the
request is still held by a listen > 0 token with the webhook.site CLI
attached. For canned replies use configure_webhook or a modify_response
custom action instead.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `request_id` | string | yes |  |
| `note` | string or object or array of any |  |  |
| `response_content` | string or object or array of any |  |  |
| `response_status` | integer |  |  |
| `response_headers` | object |  |  |

## `wait_for_email`

*read-only*

Wait for a sign-up, verify, magic-link, or password-reset email (1-120s).

Call this after the user (or you) submitted {token}@email.webhook.site
on a website. Returns subject, sender, spam/DKIM checks, a truncated
text preview, attachments, extracted confirm / reset / login URLs, and
verification_codes (OTP). Next: follow_email_link, or type the code.
HTML is omitted; use export_webhook_data for the full message. Set
return_existing=true if the email already arrived. If there is no token
yet, create_webhook first.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `timeout_seconds` | integer |  | `60` |
| `extract_links` | boolean |  | `True` |
| `return_existing` | boolean |  | `False` |

## `wait_for_request`

*read-only*

Wait until a new HTTP (or DNS) callback hits the webhook (1-120s).

Use after giving a site the webhook URL. Listens on webhook.site's
socket and falls back to polling. Bodies are truncated and HTML is
omitted; use export_webhook_data for the full dump. For verification /
magic-link / password-reset mail, use wait_for_email instead. Set
return_existing=true if the request may already be there.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `webhook_token` | string | yes |  |
| `timeout_seconds` | integer |  | `60` |
| `request_type` | `web` | `email` | `dns` |  |  |
| `return_existing` | boolean |  | `False` |
