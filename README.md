# StickyPins


# Final Version as of November 14th

This Bot was built to serve the need for a sticky bot at a large scale with it being allocated only to one guild.

It runs 1 main commands, accessible to everyone, and 2 other commands, that are not accesible to everyone and remain for maintainence purposes.

## -sticky

When a message is replied upon with this command, the bot automatically sets it as the sticky message, completing the steps of rewriting the solution msg in a Embed Message that the bot can post, pinning that embed msg, and constantly deleting it and reposting when messages are sent to always keep it at the bottom and always visible to newcomers.

### If a Pre-Existing Sticky Message is within a given thread:

In the case that this happens:

The bot will DM the user and ask for a confirmation about if they want to change the stickied message, with the choice of either reacting to either the Check Mark Reaction, OR the Cross Reaction. If The check mark reaction is pressed, it will replace the set sticky message's text and change it to the new sticky message within the database. After this is done, the code will auto-update the sticky!

##@stickypins and -solution Added

This was done as per a request.
