const { ReplayAnalysis } = require("fortnite-replay-analysis");

async function main() {
    const replayPath = process.argv[2];
    if (!replayPath) {
        console.error(JSON.stringify({ error: "No replay path provided" }));
        process.exit(1);
    }

    try {
        const { processedPlacementInfo, processedPlayerInfo, rawReplayData } = await ReplayAnalysis(replayPath, {
            bot: true,
            sort: true
        });

        const response = {
            success: true, 
            data: processedPlacementInfo,
            players: processedPlayerInfo,
            eliminations: rawReplayData?.Eliminations || [],
            killFeed: rawReplayData?.KillFeed || [],
            gameData: rawReplayData?.GameData || null,
            debug: {
                eliminationCount: rawReplayData?.Eliminations?.length || 0,
                killFeedCount: rawReplayData?.KillFeed?.length || 0,
                playerCount: rawReplayData?.PlayerData?.length || 0,
                rawKeys: rawReplayData ? Object.keys(rawReplayData) : []
            }
        };

        if (process.env.REPLAY_INCLUDE_RAW === "1") {
            response.rawDebug = {
                Eliminations: rawReplayData?.Eliminations || [],
                KillFeed: rawReplayData?.KillFeed || [],
                PlayerData: rawReplayData?.PlayerData || [],
                GameData: rawReplayData?.GameData || null
            };
        }

        console.log(JSON.stringify(response));
    } catch (e) {
        console.error(JSON.stringify({ error: e.message }));
        process.exit(1);
    }
}

main();
