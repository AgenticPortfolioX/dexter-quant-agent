const https = require('https');
const { GoogleAuth } = require('google-auth-library');

const SERVICE_ACCOUNT_PATH = 'C:/users/jmgra/antigravity/antigravity-deepseek.json';
const PROJECT_ID = 'n8n-1st-creation';
const LOCATION = 'global';
const ENDPOINT = `https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/${LOCATION}/endpoints/openapi/chat/completions`;

async function test(modelName) {
    const auth = new GoogleAuth({
        keyFile: SERVICE_ACCOUNT_PATH,
        scopes: ['https://www.googleapis.com/auth/cloud-platform'],
    });
    const client = await auth.getClient();
    const tokenResponse = await client.getAccessToken();
    const token = tokenResponse.token;

    const data = JSON.stringify({
        model: modelName,
        messages: [{ role: "user", content: "Hi" }]
    });

    const options = {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        }
    };

    console.log(`\n--- Testing model: ${modelName} ---`);

    return new Promise((resolve) => {
        const req = https.request(ENDPOINT, options, (res) => {
            let body = '';
            res.on('data', (chunk) => body += chunk);
            res.on('end', () => {
                console.log(`STATUS: ${res.statusCode}`);
                if (res.statusCode === 200) {
                    console.log(`✅ SUCCESS!`);
                } else {
                    try {
                        const err = JSON.parse(body);
                        console.log(`❌ FAILED: ${err[0].error.message}`);
                    } catch {
                        console.log(`❌ FAILED: ${body}`);
                    }
                }
                resolve();
            });
        });
        req.on('error', (e) => {
            console.error(e);
            resolve();
        });
        req.write(data);
        req.end();
    });
}

async function runAll() {
    const models = [
        "deepseek-ai/deepseek-v3.2-maas",
        "deepseek-ai/deepseek-r1-maas"
    ];
    for (const m of models) {
        await test(m);
    }
}

runAll();
