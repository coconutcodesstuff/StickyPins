# StickyPins


# Final Version as of November 22nd 2025

This Bot was built to serve the need for a sticky bot at a large scale with it being allocated only to one guild.

It runs 1 main commands(2 commands also serve the same purpose as it), accessible to everyone, and 2 other commands, that are not accesible to everyone and remain for maintainence purposes.

## -sticky

When a message is replied upon with this command, the bot automatically sets it as the sticky message, completing the steps of rewriting the solution msg in a Embed Message that the bot can post, pinning that embed msg, and constantly deleting it and reposting when messages are sent to always keep it at the bottom and always visible to newcomers.

### If a Pre-Existing Sticky Message is within a given thread:

In the case that this happens:

The bot will DM the user and ask for a confirmation about if they want to change the stickied message, with the choice of either reacting to either the Check Mark Reaction, OR the Cross Reaction. If The check mark reaction is pressed, it will replace the set sticky message's text and change it to the new sticky message within the database. After this is done, the code will auto-update the sticky!

## @stickypins and -solution Added

This was done as per a request. Both Serve the same purpose as -sticky

## -deactivate Added

This was done to make sure that threads can be deactivated incase it is ever required

# All future Updates Below!

## [UPD]22 November 2025 -> -stats and -sigs!

### -stats

This is used to view stats about the bot, such as uptime, dev, info about finding bugs and vulnerabilities, etc! Will be actively further developed as per requirements!

### -sigs

Used to give members particular roles depending on if there team is registered in a set of signature vex events. Each signature role has its own role with the exception of Kalahari Classic (Well its kind of misleading, but Kalahari Classic has both V5 and IQ Events, so no matter which one of those events you are particiapating in, it will set you to only the Kalahari Classic Role rather then independent roles for each event(V5 And IQ). holy yap....)

This uses the /events/{id}/teams, from the Robot Events API End point to retrieve all teams participating in the {ID} Event(The ID is hardcoded as its not a value that can change). Whenever a team is inputted, it retrieves the teams in all those events and checks if the inputted team # is in any of the events, if it is, the respective role is given! Extra Sumbissions will update your roles accordingly, which includes roles being removed, and given as per the new team #. If the same team # is inputted, nothing changes!
