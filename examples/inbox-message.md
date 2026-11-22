---
from: feishu
source: feishu
feishu_chat_id: oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
feishu_message_id: om_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
feishu_chat_type: group
feishu_sender: ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
feishu_sender_name: Example User
feishu_mentions: Teammate=ou_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
feishu_reply_to: om_zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz
feishu_thread_id: omt_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
---

@Teammate please check the latest run and reply here.

---
System note: sender display name: Example User
System note: thread context (chronological; use for follow-ups):
> [Example User] Starting the nightly verification run.
> [bot] Tracking run #42; will report when checks complete.
System note: quoted parent message (target of 'this/that/above'):
> [bot] Tracking run #42; will report when checks complete.
System note: mentioned users (use <at user_id="open_id">Name</at> to mention): Teammate=ou_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
System note: reply ONLY to this exact message with:
```bash
printf '%s\n' "<reply>" | scripts/feishu-reply.sh oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx om_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx --stdin
```
Do not reuse IDs from another message, and do not use cryo-agent send for Feishu replies.
