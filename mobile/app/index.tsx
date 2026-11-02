import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function Home() {
  return <SafeAreaView style={s.safe}><ScrollView contentContainerStyle={s.body}>
    <Text style={s.title}>Bruno AI Workforce</Text><Text style={s.label}>Offline operator guide</Text>
    <Text style={s.text}>This preview is not connected to your workforce account. It cannot show live status, place calls, or change automation settings.</Text>
    <View style={s.card}><Text style={s.label}>Automatic calls and forwarding</Text><Text style={s.text}>The web dashboard switch pauses scheduled auto-dialing and routes supported inbound call-backs to voicemail. It does not terminate calls already in progress. Manual calls, test calls, and voicemail recording are separate actions.</Text></View>
    <View style={s.card}><Text style={s.label}>Email and text messages</Text><Text style={s.text}>Pausing automatic calls does not pause email or SMS. Review those controls separately in the authenticated web dashboard.</Text></View>
    <View style={s.card}><Text style={s.label}>Before an action</Text><Text style={s.text}>Confirm the recipient, callback number, account and consent in the dashboard. This mobile preview requests no microphone, contacts, or notification permissions.</Text></View>
  </ScrollView></SafeAreaView>;
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0b1625' },
  body: { padding: 24, gap: 16 },
  title: { color: '#fff', fontSize: 30, fontWeight: '700' },
  text: { color: '#dce6f0', fontSize: 16, lineHeight: 24 },
  label: { color: '#f4ca83', fontSize: 16, fontWeight: '600' },
  card: { padding: 18, gap: 10, backgroundColor: '#172b40', borderRadius: 12 },
  input: { color: '#fff', borderColor: '#a5bbce', borderWidth: 1, borderRadius: 8, padding: 12, fontSize: 16 },
});
