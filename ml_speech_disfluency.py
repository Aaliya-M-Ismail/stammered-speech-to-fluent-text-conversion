import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
import librosa
import librosa.display
import warnings
import joblib
import os
warnings.filterwarnings('ignore')



class BOLIDatasetLoader:
    
    def __init__(self, dataset_path='./data/boli_dataset'):
        self.dataset_path = dataset_path
        self.data = None
        self.labels = None
    
    def load_transcriptions(self):
        with open(f'{self.dataset_path}/transcriptions.txt', 'r') as f:
            transcriptions = f.readlines()
        return transcriptions
    
    def load_labels(self):
        labels_df = pd.read_csv(f'{self.dataset_path}/labels.csv')
        return labels_df
    
    def load_disfluency_types(self):
        disfluency_types_df = pd.read_csv(f'{self.dataset_path}/disfluency_types.csv')
        return disfluency_types_df
    
    def load_dataset(self):
        print(f"Loading BOLI dataset from {self.dataset_path}...")
        
        transcriptions = self.load_transcriptions()
        labels = self.load_labels()
        disfluency_types = self.load_disfluency_types()
        
        self.data = pd.DataFrame({
            'transcription': transcriptions,
            'disfluency': labels['disfluency'].values,
            'disfluency_type': labels['type'].values,
            'speaker_id': labels['speaker_id'].values,
            'duration': labels['duration'].values
        })
        
        print(f"Dataset loaded successfully: {len(self.data)} samples")
        return self.data
    
    def load_audio_features(self):
        print("Extracting audio features from BOLI dataset...")
        
        audio_features = pd.read_csv(f'{self.dataset_path}/audio_features.csv')
        
        for col in audio_features.columns:
            if col not in self.data.columns:
                self.data[col] = audio_features[col]
        
        print(f"Audio features extracted: {len(audio_features.columns)} features per sample")
        return self.data



class DisfluencyFeatureExtractor:
    
    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=50)
        self.label_encoder = LabelEncoder()
    
    def extract_text_features(self, texts):
        print("Extracting text features (TF-IDF)...")
        return self.vectorizer.fit_transform(texts).toarray()
    
    def extract_linguistic_features(self, texts):
        print("Extracting linguistic features...")
        features = []
        
        for text in texts:
            repetitions = text.count('-')
            fillers = sum(1 for word in text.split() if word in ['um', 'uh', 'er', 'uh-huh'])
            prolongations = text.count('h')
            
            features.append([repetitions, fillers, prolongations])
        
        return np.array(features)
    
    def combine_features(self, text_features, linguistic_features):
        return np.hstack([text_features, linguistic_features])



class DisfluencyDetectionModel:
    
    def __init__(self, model_type='random_forest'):
        self.model_type = model_type
        self.model = None
        self.scaler = StandardScaler()
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None
        self.history = {}
    
    def prepare_data(self, X, y, test_size=0.2, random_state=42):
        print(f"Preparing data with {test_size*100}% test split...")
        
        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state
        )
        
        self.X_train = self.scaler.fit_transform(self.X_train)
        self.X_test = self.scaler.transform(self.X_test)
        
        print(f"Training set: {self.X_train.shape}")
        print(f"Testing set: {self.X_test.shape}")
    
    def build_model(self):
        print(f"Building {self.model_type} model...")
        
        if self.model_type == 'random_forest':
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                random_state=42,
                n_jobs=-1
            )
        elif self.model_type == 'gradient_boosting':
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5,
                random_state=42
            )
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")
    
    def train(self, epochs=10):
        print(f"Training {self.model_type} model for {epochs} epochs...")
        
        for epoch in range(epochs):
            self.model.fit(self.X_train, self.y_train)
            
            train_pred = self.model.predict(self.X_train)
            train_acc = accuracy_score(self.y_train, train_pred)
            
            test_pred = self.model.predict(self.X_test)
            test_acc = accuracy_score(self.y_test, test_pred)
            
            self.history[f'epoch_{epoch}'] = {
                'train_acc': train_acc,
                'test_acc': test_acc
            }
            
            if (epoch + 1) % 2 == 0:
                print(f"Epoch {epoch + 1}/{epochs} - Train Acc: {train_acc:.4f}, Test Acc: {test_acc:.4f}")
        
        print("Training completed!")
    
    def evaluate(self):
        print("\n" + "="*50)
        print("MODEL EVALUATION")
        print("="*50)
        
        y_pred = self.model.predict(self.X_test)
        y_pred_proba = self.model.predict_proba(self.X_test)
        
        accuracy = accuracy_score(self.y_test, y_pred)
        precision = precision_score(self.y_test, y_pred)
        recall = recall_score(self.y_test, y_pred)
        f1 = f1_score(self.y_test, y_pred)
        
        print(f"Accuracy:  {accuracy:.4f}")
        print(f"Precision: {precision:.4f}")
        print(f"Recall:    {recall:.4f}")
        print(f"F1-Score:  {f1:.4f}")
        
        print("\nConfusion Matrix:")
        cm = confusion_matrix(self.y_test, y_pred)
        print(cm)
        
        return {
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'confusion_matrix': cm
        }
    
    def predict(self, X):
        X_scaled = self.scaler.transform(X)
        predictions = self.model.predict(X_scaled)
        probabilities = self.model.predict_proba(X_scaled)
        return predictions, probabilities
    
    def save_model(self, filepath='model.h5'):
        print(f"Saving model to {filepath}...")
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'model_type': self.model_type,
            'history': self.history
        }
        joblib.dump(model_data, filepath)
        print(f"Model saved successfully to {filepath}")
    
    @classmethod
    def load_model(cls, filepath='model.h5'):
        print(f"Loading model from {filepath}...")
        if not os.path.exists(filepath):
            print(f"Error: File {filepath} not found")
            return None
        
        model_data = joblib.load(filepath)
        
        instance = cls(model_type=model_data['model_type'])
        instance.model = model_data['model']
        instance.scaler = model_data['scaler']
        instance.history = model_data['history']
        
        print(f"Model loaded successfully from {filepath}")
        return instance



class DisfluencyCorrection:
    
    def __init__(self):
        self.correction_rules = {
            'repetition': self._correct_repetition,
            'filler': self._correct_filler,
            'prolongation': self._correct_prolongation
        }
    
    def _correct_repetition(self, text):
        return text.replace('-', '')
    
    def _correct_filler(self, text):
        fillers = ['um ', 'uh ', 'er ', 'uh-huh', 'er-uh']
        corrected = text
        for filler in fillers:
            corrected = corrected.replace(filler, '')
        return corrected
    
    def _correct_prolongation(self, text):
        return text.replace('-', '')
    
    def correct_speech(self, text, disfluency_type='repetition'):
        if disfluency_type in self.correction_rules:
            return self.correction_rules[disfluency_type](text)
        return text



def main():
    
    print("="*50)
    print("SPEECH DISFLUENCY DETECTION & CORRECTION")
    print("="*50)
    
    print("\n[STEP 1] Loading BOLI Dataset")
    print("-"*50)
    loader = BOLIDatasetLoader()
    dataset = loader.load_dataset()
    dataset = loader.load_audio_features()
    
    print(dataset.head())
    
    print("\n[STEP 2] Feature Engineering")
    print("-"*50)
    extractor = DisfluencyFeatureExtractor()
    
    text_features = extractor.extract_text_features(dataset['transcription'].tolist())
    linguistic_features = extractor.extract_linguistic_features(dataset['transcription'].tolist())
    combined_features = extractor.combine_features(text_features, linguistic_features)
    
    print(f"Text features shape: {text_features.shape}")
    print(f"Linguistic features shape: {linguistic_features.shape}")
    print(f"Combined features shape: {combined_features.shape}")
    
    print("\n[STEP 3] Training Detection Model")
    print("-"*50)
    detection_model = DisfluencyDetectionModel(model_type='random_forest')
    detection_model.prepare_data(combined_features, dataset['disfluency'].values)
    detection_model.build_model()
    detection_model.train(epochs=5)
    
    print("\n[STEP 4] Model Evaluation")
    print("-"*50)
    metrics = detection_model.evaluate()
    
    print("\n[STEP 5] Saving Trained Model")
    print("-"*50)
    detection_model.save_model('model.h5')
    
    print("\n[STEP 6] Loading Saved Model")
    print("-"*50)
    loaded_model = DisfluencyDetectionModel.load_model('model.h5')
    
    print("\n[STEP 7] Making Predictions on Test Set")
    print("-"*50)
    predictions, probabilities = loaded_model.predict(loaded_model.X_test)
    
    for i in range(min(5, len(predictions))):
        actual = loaded_model.y_test[i]
        predicted = predictions[i]
        confidence = probabilities[i][predicted]
        print(f"Sample {i+1}: Predicted={predicted}, Actual={actual}, Confidence={confidence:.4f}")
    
    print("\n[STEP 8] Disfluency Correction")
    print("-"*50)
    corrector = DisfluencyCorrection()
    
    test_texts = [
        "The qu-quick brown fox",
        "I like to um to go",
        "She ha-has a garden"
    ]
    
    for text in test_texts:
        corrected = corrector.correct_speech(text, disfluency_type='repetition')
        print(f"Original:  {text}")
        print(f"Corrected: {corrected}\n")
    
    print("="*50)
    print("TRAINING AND TESTING COMPLETED!")
    print("="*50)


if __name__ == "__main__":
    main()
