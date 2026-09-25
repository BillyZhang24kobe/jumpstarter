const messagesContainer = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const imageInput = document.getElementById('image-input');
const sendMessageButton = document.getElementById('send-message');


function getChatHistory(messagesContainer){
    let chatHistory = [];
    for (let i = 0; i < messagesContainer.children.length; i++) {
        const messageGroup = messagesContainer.children[i];
        const message = messageGroup.children[0];
        if (messageGroup.className.includes('user')) {
            chatHistory.push({'user': message.textContent});
        } else if (messageGroup.className.includes('bot')) {
            chatHistory.push({'bot': message.textContent});
        }
    }
    return chatHistory;
}

function respond(prompt){

    // get current tree structure in plain text
    let treeTexts = generateTreeString(nodeMap['level-1-0-0']);

    // check if prevNode contains answer draft
    let prevNodeAnswerDraft = '';
    let prevNodeSubGoal = '';
    if (prevNode !== null && prevNode !== undefined) {
        prevNodeAnswerDraft = prevNode.answer_draft;
        prevNodeSubGoal = prevNode.text;
    }

    // record chat history from both user and bot and store them as a list of dictionaries [{'user': 'message', 'bot': 'message'}, ...]
    let chatHistory = [];
    if (messagesContainer.children.length > 0) {
        chatHistory = getChatHistory(messagesContainer);
        console.log(`Current chat history: ${chatHistory}`)
    }

    // access all variables
    const purpose = document.getElementById('purpose').innerText;
    const action = currentOption;
    const sub_goal = `${currNode.text}`;
    const answer_draft = $("#answer-draft").val();
    const prev_answer_draft = prevNodeAnswerDraft;
    const currTreeTexts = treeTexts;
    const deadline = `${currNode.deadline}`;
    const description = `${currNode.description}`;
    
    let data = {
        "purpose":purpose, "sub_goal":sub_goal, "answer_draft":answer_draft, "prev_answer_draft":prev_answer_draft, "prev_sub_goal":prevNodeSubGoal, "curr_tree_texts": currTreeTexts, "deadline": deadline, "description": description, "action": action,
        "prompt": prompt, "chat_history": chatHistory
    }
    console.log(data)
    $.ajax({
        type: "POST",
        url: "/chatresponse",                
        dataType : "json",
        contentType: "application/json; charset=utf-8",
        
        data : JSON.stringify(data),
        beforeSend: function () { 
            $("#spinner-div").show()
        },
        success: function(data, text){
            console.log("Got response from chatbot ... ")
            console.log(data)
            const botMessageGroup = document.createElement('div');
            botMessageGroup.className = 'message-group bot';
        
            const botMessage = document.createElement('div');
            botMessage.className = 'message bot-message';
            // detect if data is a string or a dictionary
            botMessage.innerHTML = data['response'].replace(/\n/g, "<br/>");
            botMessageGroup.appendChild(botMessage);
            messagesContainer.appendChild(botMessageGroup);
        },
        error: function(request, status, error){
            console.log("Error");
            console.log(request)
            console.log(status)
            console.log(error)
        },
        complete: function () { 
            $("#spinner-div").hide()
        },
    }); 
}


function onsend(){
    
    const message = messageInput.value.trim();
    // const imageFile = imageInput.files[0];
    console.log(message)

    const userMessageGroup = document.createElement('div');
    userMessageGroup.className = 'message-group user';

    if (message) { // only message
        const userMessage = document.createElement('div');
        userMessage.className = 'message user-message';
        userMessage.textContent = message;
        userMessageGroup.appendChild(userMessage);
      
        respond(message);
    }

    messagesContainer.appendChild(userMessageGroup);

    // Clear the message input field
    messageInput.value = '';

    // Scroll to the bottom of the messages container
    messagesContainer.scrollTop = messagesContainer.scrollHeight;        
  }

sendMessageButton.addEventListener('click', () => {
    onsend();
});
messageInput.addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
        onsend();
    }
});