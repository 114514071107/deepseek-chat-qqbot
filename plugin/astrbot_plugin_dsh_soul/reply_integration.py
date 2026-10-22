"""Versioned AstrBot 4.29.1 reply integration, in memory only.

No generic event callback guarantees finally-on-error or an API receipt. These
three narrow wrappers consume plans before empty-chain skipping, replace raw
agent history, and clean up even if the model/tools never produce a response.
"""
import functools
from task_runtime import work_context


def install_reply_adapters():
    from astrbot.core.pipeline.respond.stage import RespondStage
    from astrbot.core.pipeline.scheduler import PipelineScheduler
    from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import InternalAgentSubStage
    from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import QQOfficialMessageEvent

    if not getattr(QQOfficialMessageEvent.send,'_dsh_reply_adapter',False):
        event_send=QQOfficialMessageEvent.send
        @functools.wraps(event_send)
        async def send(event,chain):
            plugin=event.get_extra('_dsh_reply_owner')
            if not plugin: return await event_send(event,chain)
            token=event.get_extra('_dsh_work')
            if token is None: return None
            with work_context(token,event):
                plugin.runtime.check(token)
                result=await plugin._send(event.get_extra('_dsh_scope').target,chain)
                if result:
                    plugin._record_assistant_turn(token.key,chain.get_plain_text() or '[媒体]',result,request_id=token.request)
                return result
        send._dsh_reply_adapter=True
        QQOfficialMessageEvent.send=send

    if not getattr(RespondStage.process,'_dsh_reply_adapter',False):
        original=RespondStage.process
        @functools.wraps(original)
        async def respond(self,event):
            plugin=event.get_extra('_dsh_reply_owner')
            if plugin and event.get_extra('_dsh_reply_plan') is not None:
                await plugin._complete_reply(event)
                event.set_result(None)
                return
            return await original(self,event)
        respond._dsh_reply_adapter=True
        RespondStage.process=respond

    if not getattr(InternalAgentSubStage._save_to_history,'_dsh_reply_adapter',False):
        save=InternalAgentSubStage._save_to_history
        @functools.wraps(save)
        async def history(self,event,req,*args,**kwargs):
            plugin=event.get_extra('_dsh_reply_owner')
            if plugin:
                # A completion_text-only response can become completely empty
                # in capture. The runner then yields no RespondStage at all.
                if not event.is_stopped():
                    await plugin._complete_reply(event)
                await plugin._persist_framework_reply(event,req)
                return
            return await save(self,event,req,*args,**kwargs)
        history._dsh_reply_adapter=True
        InternalAgentSubStage._save_to_history=history

    if not getattr(PipelineScheduler.execute,'_dsh_reply_adapter',False):
        execute=PipelineScheduler.execute
        @functools.wraps(execute)
        async def pipeline(self,event):
            try:
                result=await execute(self,event)
                plugin=event.get_extra('_dsh_reply_owner')
                if plugin and not event.is_stopped():
                    await plugin._complete_reply(event)
                return result
            finally:
                plugin=event.get_extra('_dsh_reply_owner')
                if plugin: plugin._finish_reply(event)
        pipeline._dsh_reply_adapter=True
        PipelineScheduler.execute=pipeline
