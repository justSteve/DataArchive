I'd like to create an app that downloads the full history of a given channel on Discord.

I'll choose to use Playwrite. I propose that our high level strategy be something like: 
Launch a browser (headless or visible for debugging)
You manually log into Discord (or we store cookies after first login)
Navigate to the target channel
Scroll up repeatedly to load message history
Scrape the DOM for message content, timestamps, authors
Save to JSON/CSV/database

But our upcoming Superpowers Brainstorming session will refine that.

The app needs to capture as much of the meta data per post as possible -- let me record the various reactions and replies that a given post gets.

But the nature of the range of channels I belong to do not all require the same kind of attention. Some need to record details of who reacted with what emogi, others will not require that level of detail. So that filter flag has to be implemented.

All channels will want to capture the 'replying to...' or 'is a reply to...' meta date. 

A fairly rich db schema will be required to re-assemble the thread meta data. Discord has threads. Most users do not use it and a thread can only be constructed by the 'replied to' sort of meta date. Apply deep thought to how there 'non-thread' passages can be linked.

In constructing the db schema, error to the side of verbosity. 

This represents the 'domain' aspect of the project. The packages referred to in the 'blueprint' documents will need to be developed at a later date but they will be a part of this project.