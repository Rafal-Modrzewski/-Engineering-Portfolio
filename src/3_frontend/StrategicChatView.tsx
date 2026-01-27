// src/3_frontend/StrategicChatView.tsx

/*
 * StrategicChatView
 * Real-time chat interface with optimistic UI updates and robust error recovery.
 * 
 * Features:
 * - Optimistic state management: Immediate UI feedback before API confirmation.
 * - Auto-scrolling and latency handling: Maintains user context during async operations.
 * - Strongly typed interfaces: Ensures integration safety with backend API.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import apiService from '../services/apiService'; 
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Loader2, Send, RefreshCw, ArrowLeft } from 'lucide-react';
import { cn } from "@/lib/utils"; // For conditional class names
import { useAuth } from '../contexts/AuthContext'; // To get current user's name/avatar

// --- Types ---
export interface ChatMessage {
    id: string; // Unique ID for React keys
    sender: 'user' | 'ai';
    text: string;
    timestamp: string; // ISO string 
    username?: string; // Display name for the sender
    avatar?: string; // URL for the sender's avatar
}

interface StrategicChatViewProps {
    campaignId: string; // ID of the 'strategic_discussion' campaign
    discussionTitle: string; // Title to display in the header (e.g., "Discussing: Refine C-Suite Brand Voice")
    initialMessages?: ChatMessage[]; //  initial messages to pre-populate the chat
    onClose: () => void; // Callback to navigate back to the dashboard or previous view
}

// --- Component ---
const StrategicChatView: React.FC<StrategicChatViewProps> = ({
    campaignId,
    discussionTitle,
    initialMessages = [],
    onClose
}) => {
    const { currentUser } = useAuth(); // Get current Firebase user for username/avatar

    // --- State Management: Messages, Loading, and Error Handling ---

    const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
    const [newMessage, setNewMessage] = useState("");
    const [isSending, setIsSending] = useState(false); // State for loading/sending messages
    const [error, setError] = useState<string | null>(null); // Error message for chat interactions

    // Ref for the chat container to enable auto-scrolling
    const chatContainerRef = useRef<null | HTMLDivElement>(null);
    const messagesEndRef = useRef<null | HTMLDivElement>(null); // For scrolling to the very bottom

    // Effect to scroll to the bottom whenever messages change
    const scrollToBottom = useCallback(() => {
        if (chatContainerRef.current) {
            chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
        }
    }, []);

    useEffect(() => {
        scrollToBottom();
    }, [messages, scrollToBottom]);
    

    // --- Message Sending Logic ---
    const handleSendMessage = async () => {
        if (!newMessage.trim() || isSending) return; // Prevent sending empty messages or multiple sends

        const userMsg: ChatMessage = {
            id: `user-${Date.now()}`, // Unique ID for React key
            sender: 'user',
            text: newMessage.trim(),
            timestamp: new Date().toISOString(),
            username: currentUser?.displayName || currentUser?.email?.split('@')[0] || "You", // Get user's display name
            avatar: `https://avatar.vercel.sh/${currentUser?.email || 'user'}.png?s=32` // Vercel avatar service
        };

        // --- Optimistic UI Update ---
            // Update local state immediately and handle rollback on API failure 
            // to ensure UI consistency.

        setMessages(prev => [...prev, userMsg]); // Optimistically add user message to UI
        const currentInput = newMessage.trim(); // Capture current input for API call
        setNewMessage(""); // Clear input field
        setIsSending(true); // Set sending state
        setError(null); // Clear previous errors

        try {
            // Call the backend endpoint to continue the chat
            // This endpoint  appends the user's message to conversation_history,
            // trigger AI response, append AI response, and return the AI's message.
            const response = await apiService.post(
                `/campaign/${campaignId}/chat/message`, // UPDATED ENDPOINT
                { user_message: { role: "user", content: currentInput, username: userMsg.username } }
            );
            
            // Assuming the backend returns an object with an 'ai_message' field containing the AI's reply text
            const aiReplyContent = response.data.ai_message;
            if (aiReplyContent && typeof aiReplyContent === 'string') {
                const aiMsg: ChatMessage = {
                    id: `ai-${Date.now()}`, // Unique ID for AI message
                    sender: 'ai',
                    text: aiReplyContent,
                    timestamp: new Date().toISOString(),
                    username: "AI Strategist", // AI's name
                    avatar: "/ai-avatar.png" // Path to AI avatar image
                };
                setMessages(prev => [...prev, aiMsg]); // Add AI's message to UI
            } else {
                throw new Error("Invalid AI response structure."); // Handle unexpected AI response
            }
        } catch (apiError) {
            console.error("Error sending message:", apiError);
            setError("Failed to get AI response. Please try again.");
            // Revert the optimistic update on failure. This is key for UI trust.
            setMessages(prev => prev.filter(msg => msg.id !== userMsg.id));
            setNewMessage(currentInput); // Restore input for user to retry
        } finally {
            setIsSending(false); // Reset sending state
        }
    };

    // --- Regenerate Logic ---
    // ... (The logic here is an example of handling a more complex user interaction)

    const handleRegenerate = async () => {
        if (isSending || messages.filter(m => m.sender === 'ai').length === 0) return; // Prevent if already sending or no AI messages to regenerate

        // Find the last user message to provide context for regeneration
        const lastUserMessage = [...messages].reverse().find(m => m.sender === 'user');
        if (!lastUserMessage) {
            setError("No previous user message to regenerate response from.");
            return;
        }

        // Optimistically remove the last AI message from UI if it exists
        if (messages.length > 0 && messages[messages.length - 1].sender === 'ai') {
            setMessages(prev => prev.slice(0, -1));
        }
        
        setIsSending(true); // Set sending state
        setError(null); // Clear errors

        try {
            // Call backend with a "regenerate" action, providing context (e.g., last user message)
            // This endpoint removes the last AI entry from history, regenerate, and add new AI entry.
            const response = await apiService.post(
                `/campaign/${campaignId}/chat/regenerate`, 
                { last_user_message_content: lastUserMessage.text } // Payload with context for regeneration
            );
            
            const aiReplyContent = response.data.ai_message; // Assuming response structure
            if (aiReplyContent && typeof aiReplyContent === 'string') {
                const aiMsg: ChatMessage = {
                    id: `ai-regen-${Date.now()}`, // Unique ID for regenerated message
                    sender: 'ai',
                    text: aiReplyContent,
                    timestamp: new Date().toISOString(),
                    username: "AI Strategist",
                    avatar: "/ai-avatar.png"
                };
                setMessages(prev => [...prev, aiMsg]); // Add new AI message to UI
            } else {
                throw new Error("Invalid AI response structure for regeneration.");
            }
        } catch (apiError) {
            console.error("Error regenerating response:", apiError);
            setError("Failed to regenerate AI response. Please try again.");
        } finally {
            setIsSending(false); // Reset sending state
        }
    };


    return (
        <div className="flex flex-col h-screen bg-slate-100 font-sans text-slate-800">
            {/* Header */}
            <header className="bg-white shadow-md p-4 flex items-center justify-between sticky top-0 z-20 border-b border-slate-200">
                <div className="flex items-center">
                    <Button variant="ghost" size="icon" onClick={onClose} aria-label="Back to Dashboard" className="mr-2 text-slate-600 hover:bg-slate-200">
                        <ArrowLeft className="h-5 w-5" />
                    </Button>
                    <h1 className="text-xl font-semibold text-slate-800 truncate" title={discussionTitle}>{discussionTitle}</h1>
                </div>
            </header>

            {/* Chat Messages Area */}
            <div ref={chatContainerRef} className="flex-1 overflow-y-auto p-4 md:p-6 space-y-5 bg-slate-50">
                {messages.map((msg) => (
                    <div key={msg.id} className={cn("flex items-end max-w-[80%] md:max-w-[70%]", msg.sender === 'user' ? "ml-auto" : "mr-auto")}>
                        {/* AI Avatar on left */}
                        {msg.sender === 'ai' && (
                            <Avatar className="h-8 w-8 mr-2.5 flex-shrink-0 shadow">
                                <AvatarImage src={msg.avatar || "/ai-avatar.png"} alt={msg.username || "AI"} />
                                <AvatarFallback>{(msg.username || "AI").substring(0,1)}</AvatarFallback>
                            </Avatar>
                        )}
                        {/* Message Bubble */}
                        <div className={cn(
                            "p-3.5 rounded-2xl text-base leading-relaxed shadow-md",    
                            msg.sender === 'user' 
                                ? "bg-indigo-600 text-white rounded-br-lg" // User message style
                                : "bg-white text-slate-800 rounded-bl-lg border border-slate-200" // AI message style
                        )}>
                            {/* Render text with line breaks */}
                            {msg.text.split('\n').map((line, i, arr) => (
                                <span key={i}>{line}{i < arr.length - 1 && <br/>}</span>
                            ))}
                        </div>
                        {/* User Avatar on right */}
                        {msg.sender === 'user' && (
                             <Avatar className="h-8 w-8 ml-2.5 flex-shrink-0 shadow">
                                <AvatarImage src={msg.avatar || `https://avatar.vercel.sh/${currentUser?.email || 'user'}.png?s=32`} alt={msg.username || "User"} />
                                <AvatarFallback>{(msg.username || "U").substring(0,1)}</AvatarFallback>
                            </Avatar>
                        )}
                    </div>
                ))}
                <div ref={messagesEndRef} /> {/* Invisible element for scrolling */}
                {/* AI typing indicator */}
                {isSending && (messages.length === 0 || messages[messages.length -1]?.sender === 'user') && (
                    <div className="flex items-end max-w-[80%] md:max-w-[70%] mr-auto">
                        <Avatar className="h-8 w-8 mr-2.5 flex-shrink-0 shadow"><AvatarImage src="/ai-avatar.png" /><AvatarFallback>AI</AvatarFallback></Avatar>
                        <div className="p-3.5 rounded-2xl bg-white text-slate-800 rounded-bl-lg border border-slate-200 shadow-md">
                            <Loader2 className="h-5 w-5 animate-spin text-indigo-500" />
                        </div>
                    </div>
                )}
            </div>

            {/* Chat Input Area */}
            <footer className="bg-white border-t border-slate-200 p-3 md:p-4 sticky bottom-0 z-10">
                {error && <p className="text-red-600 text-xs mb-2 text-center px-2">{error}</p>}
                <div className="flex items-center space-x-2 max-w-3xl mx-auto">
                    <Input
                        type="text"
                        placeholder="Type your message here..."
                        value={newMessage}
                        onChange={(e) => setNewMessage(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && !isSending && handleSendMessage()}
                        className="flex-1 h-11 text-base rounded-lg border-slate-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/50"
                        disabled={isSending}
                        aria-label="Chat message input"
                    />
                    <Button onClick={handleSendMessage} disabled={!newMessage.trim() || isSending} className="bg-indigo-600 hover:bg-indigo-700 h-11 w-11 p-0 rounded-lg">
                        {isSending ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
                        <span className="sr-only">Send message</span>
                    </Button>
                    <Button variant="outline" onClick={handleRegenerate} disabled={isSending || messages.filter(m=>m.sender==='ai').length === 0} title="Regenerate last AI response" className="h-11 w-11 p-0 rounded-lg border-slate-300 hover:bg-slate-100">
                        <RefreshCw className="h-5 w-5 text-slate-600" />
                        <span className="sr-only">Regenerate response</span>
                    </Button>
                </div>
            </footer>
        </div>
    );
};

export default StrategicChatView;
