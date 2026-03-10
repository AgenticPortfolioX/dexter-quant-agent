import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function runTest() {
    console.log("🚀 Starting Full System Test...");

    // 1. Start Server
    const server = spawn('bun', ['run', 'server.ts'], {
        cwd: path.join(__dirname, 'dexter-core'),
        env: { ...process.env, PORT: '3000' }
    });

    let serverStarted = false;
    server.stdout.on('data', (data) => {
        const msg = data.toString();
        if (msg.includes('running on')) serverStarted = true;
    });

    // Wait for server to start (timeout 10s)
    let attempts = 0;
    while (!serverStarted && attempts < 20) {
        await new Promise(resolve => setTimeout(resolve, 500));
        attempts++;
    }

    if (!serverStarted) {
        console.error("❌ Failed to start server in time.");
        server.kill();
        process.exit(1);
    }

    console.log("✅ Server is online.");

    try {
        // 2. Send Query
        const query = "Analyze AAPL factors and run a mock backtest.";
        console.log(`\n💬 Querying Agent: "${query}"`);

        const response = await fetch("http://localhost:3000/query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${await response.text()}`);
        }

        const data = await response.json();

        console.log("\n🤖 Response received from Dexter.");

        // 3. Verification
        if (data.answer && data.answer.length > 0) {
            console.log("✅ SUCCESS: Agent returned an answer.");

            // Check for ANSI
            if (!/[\u001b\u009b]/.test(data.answer)) {
                console.log("✅ SUCCESS: Output is clean (no ANSI codes).");
            } else {
                console.warn("⚠️ WARNING: ANSI codes detected in output.");
            }

            // Check if it mentioned Qlib/Factors/Backtest (High probability if it worked)
            const text = data.answer.toLowerCase();
            if (text.includes('factor') || text.includes('backtest') || text.includes('momentum')) {
                console.log("✅ SUCCESS: Agent used quantitative reasoning/tools.");
            }
        } else {
            console.error("❌ FAILURE: Agent returned an empty response.");
        }

    } catch (err) {
        console.error("\n❌ TEST FAILED:", err.message);
    } finally {
        // 4. Shutdown
        console.log("\n🛑 Shutting down test server...");
        server.kill();
        // Give it a moment to die
        setTimeout(() => process.exit(), 1000);
    }
}

runTest();
