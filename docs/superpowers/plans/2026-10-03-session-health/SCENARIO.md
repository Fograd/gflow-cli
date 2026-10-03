# Session health scenarios

| Severity | Boundary | Expected outcome |
|---|---|---|
| Critical | Active accepted job or external browser lease | Unknown/busy, no interruption or process kill |
| Critical | Concurrent generation accepted after health precheck | Hook must serialize in existing queue or reserve before acceptance |
| Critical | Supplied profile path or arbitrary project | Reject before browser, only selected account registration allowed |
| Critical | Cookies present but native project denied | Never healthy from cookie presence; login or unknown outcome |
| High | Marker absent/replaced/identity changes | Fixed safe reason; preserve all browser data |
| High | Native project read times out or transport/selector fails | Unknown, no permanent registration downgrade, no retry |
| High | Cancellation during read or context close | Existing client teardown/lease release, no generation replay |
| High | Valid Google SSO and project access at time T | Healthy only at T; no keepalive/expiry guarantee |
| High | Exception carries tokens/URLs/account response | Whitelisted statuses only; never exception text |
| Medium | Windows/macOS/Linux profile paths | Use auth.profile_dir and shared portable bounded marker helper |
| Medium | CLI/MCP auth status remains historical cookie oracle | Documentation explicitly distinguishes native project access |
| Low | Repeated health requests | On-demand finite work; no daemon scheduler or retry storm |

Generation, CAPTCHA and download fields are absent; no batch-output state or
billable operation changes. API route integration is a separate gated task.
