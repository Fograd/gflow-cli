"""Native saved-TTS field codecs derived from the deployed frontend source.

These codecs do not dispatch generation. Preview is billable; saving an acknowledged
preview updates media visibility and workflow metadata separately.
"""

from __future__ import annotations

from typing import Any, Literal, cast
from uuid import UUID

from gflow_cli.api.character import VOICE_NAMES

PREVIEW_RPC = "no0P6"
SAVE_MEDIA_RPC = "lt8g5"
SAVE_WORKFLOW_RPC = "mYWVGd"
GET_MEDIA_RPC = "as29s"
DELETE_RPC = "cz8Z4b"
AUDIO_ACTION = "AUDIO_GENERATION"
AUDIO_MODEL = "gemini_v4s_tts_flow"


def validate_identifier(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Voice operation requires UUID identifiers")
    try:
        return str(UUID(value))
    except ValueError:
        raise ValueError("Voice operation requires UUID identifiers") from None


def _text(value: object, maximum: int, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or not value.strip():
        raise ValueError(f"{label} has an invalid length")
    return value


def preview_payload(
    project_id: str,
    *,
    preset: object,
    dialogue: str,
    performance: str,
    display_name: str,
    captcha_token: object,
) -> list[Any]:
    """Encode frontend BatchGenerateAudio fields, without sending a request."""
    project = validate_identifier(project_id)
    canonical = next(
        (
            name
            for name in VOICE_NAMES
            if isinstance(preset, str) and name.lower() == preset.lower()
        ),
        None,
    )
    if canonical is None:
        raise ValueError("Voice preset is not supported")
    dialogue = _text(dialogue, 120, "Dialogue")
    performance = _text(performance, 120, "Performance")
    display_name = _text(display_name, 200, "Voice name")
    if not isinstance(captcha_token, str) or not 1 <= len(captcha_token) <= 16384:
        raise ValueError("Voice CAPTCHA token is unavailable")
    request = [dialogue, [[canonical, display_name]], AUDIO_MODEL, performance, 2]
    context = [None, 22, None, None, None, project, None, None, None, None, [captcha_token, 1]]
    return [[request], context]


def save_payloads(
    project_id: str, media_id: str, workflow_id: str, display_name: str
) -> tuple[list[Any], list[Any]]:
    """Encode distinct media visibility and workflow-name updates after preview."""
    project = validate_identifier(project_id)
    media = validate_identifier(media_id)
    workflow = validate_identifier(workflow_id)
    name = _text(display_name, 200, "Voice name")
    metadata = [None] * 9 + [1]
    media_payload = [
        [media, None, None, None, None, metadata],
        [["media.media_metadata.visibility"]],
    ]
    workflow_payload = [[workflow, None, None, [name], project], [["metadata.display_name"]]]
    return media_payload, workflow_payload


def parse_saved_voices(payload: Any, project_id: str) -> list[dict[str, Any]]:
    """Read visible owned audio media joined to its active project workflow.

    Field positions come from the deployed protobuf classes; URLs are deliberately
    excluded from this catalog projection.
    """
    project = validate_identifier(project_id)
    if not isinstance(payload, list) or len(cast(list[Any], payload)) < 3:
        raise ValueError("Saved voice catalog has an unsupported shape")
    payload = cast(list[Any], payload)
    workflows: Any = payload[1]
    media: Any = payload[2]
    if not isinstance(workflows, list) or not isinstance(media, list):
        raise ValueError("Saved voice catalog collections are unavailable")
    names: dict[str, str] = {}
    active: set[str] = set()
    for row in cast(list[Any], workflows):
        if not isinstance(row, list) or len(cast(list[Any], row)) < 5 or row[4] != project:
            raise ValueError("Saved voice workflow ownership is unavailable")
        row = cast(list[Any], row)
        info: Any = row[3]
        if isinstance(info, list) and len(cast(list[Any], info)) >= 5 and not info[2]:
            workflow = validate_identifier(row[0])
            active.add(workflow)
            names[workflow] = info[0] if isinstance(info[0], str) else ""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in cast(list[Any], media):
        if not isinstance(row, list) or len(cast(list[Any], row)) <= 10 or row[10] is None:
            continue
        if row[1] != project:
            raise ValueError("Saved voice media ownership is unavailable")
        if row[6] is not None or row[7] is not None:
            raise ValueError("Saved voice media union is ambiguous")
        row = cast(list[Any], row)
        metadata: Any = row[5]
        audio: Any = row[10]
        if (
            not isinstance(metadata, list)
            or len(cast(list[Any], metadata)) <= 9
            or metadata[9] != 1
        ):
            continue
        if (
            not isinstance(audio, list)
            or len(cast(list[Any], audio)) != 1
            or not isinstance(audio[0], list)
        ):
            raise ValueError("Saved voice audio metadata is unavailable")
        sample = cast(list[Any], audio[0])
        media_id, workflow = validate_identifier(row[0]), validate_identifier(row[2])
        if workflow not in active:
            continue
        if media_id in seen:
            raise ValueError("Saved voice media identity is ambiguous")
        seen.add(media_id)
        result.append(
            {
                "ref": media_id,
                "project_id": project,
                "workflow_id": workflow,
                "display_name": names[workflow],
                "performance": sample[1] if len(sample) > 1 and isinstance(sample[1], str) else "",
                "dialogue": sample[6] if len(sample) > 6 and isinstance(sample[6], str) else "",
            }
        )
    return result


async def list_saved_voices(page: Any, project_id: str) -> dict[str, Any]:
    from gflow_cli.api.transports.migrated_resources import read_project_payload

    project = validate_identifier(project_id)
    rows = parse_saved_voices(await read_project_payload(page, project), project)
    return {
        "voices": rows,
        "project_id": project,
        "returned_count": len(rows),
        "scope": "selected-project visible saved-TTS snapshot",
        "complete": None,
    }


def saved_voice_detail_fields(
    payload: Any, *, project_id: str, media_id: str, workflow_id: str
) -> dict[str, Any]:
    """Exact audio arm plus source-derived playback/base-preset fields."""
    from urllib.parse import urlsplit

    project, media, workflow = (validate_identifier(v) for v in (project_id, media_id, workflow_id))
    if not isinstance(payload, list):
        raise ValueError("Saved voice detail has an unsupported shape")
    row = cast(list[Any], payload)
    if len(row) <= 10 or row[:3] != [media, project, workflow]:
        raise ValueError("Saved voice detail ownership does not match")
    if row[6] is not None or row[7] is not None:
        raise ValueError("Saved voice detail must contain only the audio media union")
    audio: Any = row[10]
    if not isinstance(audio, list) or len(cast(list[Any], audio)) != 1:
        raise ValueError("Saved voice detail audio is unavailable")
    sample: Any = cast(list[Any], audio)[0]
    if not isinstance(sample, list):
        raise ValueError("Saved voice detail audio is unavailable")
    sample = cast(list[Any], sample)

    def field(index: int) -> Any:
        return sample[index] if len(sample) > index else None

    result: dict[str, Any] = {
        "performance": field(1) if isinstance(field(1), str) else "",
        "dialogue": field(6) if isinstance(field(6), str) else "",
    }
    if isinstance(field(7), str):
        result["description"] = field(7)
    base: Any = field(4)
    speakers: Any = field(11)
    if not base and isinstance(speakers, list) and speakers:
        speaker: Any = cast(list[Any], speakers)[0]
        if isinstance(speaker, list) and speaker:
            base = cast(list[Any], speaker)[0]
    if isinstance(base, str):
        canonical = next(
            (v for v in VOICE_NAMES if v.casefold() == base.removeprefix("voices/").casefold()),
            None,
        )
        if canonical:
            result["preset_voice"] = canonical
    url: Any = field(3) or field(5)
    if url:
        if not isinstance(url, str):
            raise ValueError("Saved voice playback URL is unavailable")
        try:
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in (None, 443)
                or parsed.fragment
            ):
                raise ValueError
        except ValueError:
            raise ValueError("Saved voice playback URL is invalid") from None
        result["audio_url"] = url
    return result


async def get_saved_voice(page: Any, project_id: str, voice_id: str) -> dict[str, Any]:
    from gflow_cli.api.transports.migrated_rpc import native_rpc

    project, voice = validate_identifier(project_id), validate_identifier(voice_id)
    snapshot = await list_saved_voices(page, project)
    matches = [row for row in snapshot["voices"] if row["ref"] == voice]
    if len(matches) != 1:
        raise ValueError("Saved voice is not uniquely owned by the selected project")
    result = dict(matches[0])
    media = await native_rpc(
        page, GET_MEDIA_RPC, [voice], "/project/" + project, require_single=True
    )
    return {
        **result,
        **saved_voice_detail_fields(
            media, project_id=project, media_id=voice, workflow_id=result["workflow_id"]
        ),
    }


async def delete_saved_voice(
    page: Any, project_id: str, voice_id: str, confirm_delete: object = False
) -> dict[str, Any]:
    if confirm_delete is not True:
        raise ValueError("Saved voice deletion requires explicit confirmation")
    project, voice = validate_identifier(project_id), validate_identifier(voice_id)
    owned = await get_saved_voice(page, project, voice)
    from gflow_cli.errors import VoiceMutationUnknownError

    workflow = owned["workflow_id"]
    try:
        await _rpc(
            page, project, DELETE_RPC, [None, [workflow], project, None, None, None, [voice]]
        )
    except Exception:
        raise VoiceMutationUnknownError(
            project_id=project, phase="delete", media_id=voice, workflow_id=workflow
        ) from None
    return {"project_id": project, "deleted": [voice], "operation": "delete"}


async def _rpc(page: Any, project: str, rpc: str, args: list[Any]) -> Any:
    from gflow_cli.api.transports.batchexecute import parse_frames

    if rpc not in {PREVIEW_RPC, SAVE_MEDIA_RPC, SAVE_WORKFLOW_RPC, GET_MEDIA_RPC, DELETE_RPC}:
        raise ValueError("Unsupported saved voice operation")
    result = await page.evaluate(
        """async ({project,rpc,args}) => {
          if (location.hostname !== 'flow.google.com') throw Error('Native host required');
          const w=window.WIZ_global_data;
          const query=new URLSearchParams({rpcids:rpc,'source-path':'/project/'+project,
            bl:w.cfb2h,'f.sid':w.FdrFJe,hl:'en',rt:'c'});
          const body=new URLSearchParams({'f.req':JSON.stringify([
            [[rpc,JSON.stringify(args),null,'generic']]]),at:w.SNlM0e});
          const controller=new AbortController();
          const timer=setTimeout(()=>controller.abort(),25000);
          try {
            const response=await fetch('/_/AiSandboxAngularFrontend/data/batchexecute?'+query,
              {method:'POST',headers:{'content-type':'application/x-www-form-urlencoded;charset=UTF-8'},
               body,signal:controller.signal});
            if (!response.ok) return {status:response.status,text:''};
            const reader=response.body.getReader();const chunks=[];let size=0;
            while(true){const {done,value}=await reader.read();if(done)break;
              size+=value.length;
              if(size>262144){await reader.cancel();throw Error('Reply too large');}
              chunks.push(value);}
            const bytes=new Uint8Array(size);let offset=0;
            for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
            return {status:response.status,text:new TextDecoder().decode(bytes)};
          } finally {clearTimeout(timer);}
        }""",
        {"project": project, "rpc": rpc, "args": args},
    )
    if not isinstance(result, dict):
        raise ValueError("Saved voice operation acknowledgement is unavailable")
    result = cast(dict[str, Any], result)
    if result.get("status") != 200:
        raise ValueError("Saved voice operation acknowledgement is unavailable")
    from gflow_cli.api.transports.migrated_composer import (
        _submit_refusal,  # pyright: ignore[reportPrivateUsage]
    )

    refusal = _submit_refusal(result.get("text", ""), (rpc,))
    if refusal is not None:
        raise refusal
    for name, data in parse_frames(result.get("text", "")):
        if name == rpc:
            return data
    raise ValueError("Saved voice operation acknowledgement is unavailable")


async def _mint_audio_token(page: Any) -> str:
    import asyncio

    token = await asyncio.wait_for(
        page.evaluate(
            """async () => {
              if(location.hostname!=='flow.google.com')throw Error('Native host required');
              const script=[...document.scripts].find(s=>{
                try {const u=new URL(s.src);return u.hostname==='www.google.com'
                  &&u.pathname==='/recaptcha/enterprise.js'&&u.searchParams.has('render');}
                catch{return false;}});
              if(!script)throw Error('Native CAPTCHA unavailable');
              const key=new URL(script.src).searchParams.get('render');
              const api=window.grecaptcha?.enterprise;
              if(!api||!key||key==='explicit')throw Error('Native CAPTCHA unavailable');
              await new Promise(resolve=>api.ready(resolve));
              return await api.execute(key,{action:'AUDIO_GENERATION'});
            }"""
        ),
        timeout=15,
    )
    if not isinstance(token, str) or not token:
        raise ValueError("Native audio CAPTCHA token is unavailable")
    return token


def preview_identity(payload: Any, project_id: str) -> tuple[str, str]:
    """Read only the documented first generated media and its workflow."""
    project = validate_identifier(project_id)
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        raise ValueError("Audio preview acknowledgement has an unsupported shape")
    media = cast(list[Any], payload[0])
    if len(media) != 1 or not isinstance(media[0], list) or len(cast(list[Any], media[0])) < 3:
        raise ValueError("Audio preview acknowledgement is not a single result")
    row = cast(list[Any], media[0])
    if row[1] != project:
        raise ValueError("Audio preview belongs to an unrelated project")
    return validate_identifier(row[0]), validate_identifier(row[2])


async def create_saved_voice(
    page: Any,
    project_id: str,
    display_name: str,
    preset_voice: str,
    dialog: str,
    performance: str,
) -> dict[str, Any]:
    from gflow_cli.errors import VoiceMutationUnknownError

    project = validate_identifier(project_id)
    # Validate all public fields before navigation or minting.
    preview_payload(
        project,
        preset=preset_voice,
        dialogue=dialog,
        performance=performance,
        display_name=display_name,
        captcha_token="validation-only",
    )
    from gflow_cli.api.transports.migrated_resources import read_project_payload

    await read_project_payload(page, project)
    token = await _mint_audio_token(page)
    media_id: str | None = None
    workflow_id: str | None = None
    phase: Literal["preview", "save", "delete"] = "preview"
    try:
        reply = await _rpc(
            page,
            project,
            PREVIEW_RPC,
            preview_payload(
                project,
                preset=preset_voice,
                dialogue=dialog,
                performance=performance,
                display_name=display_name,
                captcha_token=token,
            ),
        )
        media_id, workflow_id = preview_identity(reply, project)
        # Retain these acknowledged handles before either saving metadata mutation.
        phase = "save"
        media_args, workflow_args = save_payloads(project, media_id, workflow_id, display_name)
        media_reply = await _rpc(page, project, SAVE_MEDIA_RPC, media_args)
        if (
            not isinstance(media_reply, list)
            or len(cast(list[Any], media_reply)) < 3
            or media_reply[:3] != [media_id, project, workflow_id]
        ):
            raise ValueError("Saved audio metadata acknowledgement does not match")
        workflow_reply = await _rpc(page, project, SAVE_WORKFLOW_RPC, workflow_args)
        if (
            not isinstance(workflow_reply, list)
            or len(cast(list[Any], workflow_reply)) < 5
            or workflow_reply[0] != workflow_id
            or workflow_reply[4] != project
        ):
            raise ValueError("Saved audio workflow acknowledgement does not match")
    except BaseException as error:
        import asyncio

        from gflow_cli.errors import ContentPolicyError, WafRejectionError

        if (
            phase == "preview"
            and media_id is None
            and workflow_id is None
            and isinstance(error, (WafRejectionError, ContentPolicyError))
        ):
            raise

        typed = VoiceMutationUnknownError(
            project_id=project, phase=phase, media_id=media_id, workflow_id=workflow_id
        )
        if isinstance(error, asyncio.CancelledError):
            vars(error)["gflow_saved_voice_unknown"] = typed
            raise
        if not isinstance(error, Exception):
            raise
        raise typed from None
    return {
        "ref": media_id,
        "workflow_id": workflow_id,
        "project_id": project,
        "display_name": display_name,
        "dialogue": dialog,
        "performance": performance,
        "preset_voice": preset_voice.lower(),
        "operation": "create",
    }
