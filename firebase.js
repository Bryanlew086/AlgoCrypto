// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyDyNL8LXlz8QSGMdMV1todW52uAR9ZYhkE",
  authDomain: "algocrypto-eaa8c.firebaseapp.com",
  projectId: "algocrypto-eaa8c",
  storageBucket: "algocrypto-eaa8c.firebasestorage.app",
  messagingSenderId: "418106626029",
  appId: "1:418106626029:web:9d278df69fb0a7dd10e1e4",
  measurementId: "G-CWJECX4N3R"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);