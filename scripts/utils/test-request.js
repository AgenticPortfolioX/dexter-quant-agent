const query = "What are the top 3 tech stocks by market cap currently?";

console.log(`Sending query to server: "${query}"...`);

fetch("http://localhost:3000/query", {
    method: "POST",
    headers: {
        "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
})
    .then((res) => {
        if (!res.ok) {
            throw new Error(`HTTP error! status: ${res.status}`);
        }
        return res.json();
    })
    .then((data) => {
        console.log("\nResponse from Dexter:");
        console.log("--------------------");
        console.log(data.answer);
        console.log("--------------------");
    })
    .catch((err) => {
        console.error("\nError connecting to server:", err.message);
        console.log("Make sure the server is running with 'bun run start:server' inside dexter-core.");
    });
