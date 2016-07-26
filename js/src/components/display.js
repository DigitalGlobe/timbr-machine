import React from 'react';
import dispatcher from './dispatcher.js';

class DisplayStatus extends React.Component {

  constructor( props ) {
    super( props );
    this.state = { 
      status: {}
    };
  }

  componentWillMount(){
    dispatcher.register( payload => {
      if ( payload.actionType === 'display_update' ) {
        this.setState({ status: payload.data.status })
      }
    } );
  }

  render() {
    const { status } = this.state;
    console.log(status)
    return ( 
      <div id="timbr_machine_status">
        <h2>Timbr Machine Status</h2>
        { Object.keys( status ).map( ( field, i ) => (
            <div key={ i }>
              <span className='field-name'>{field}:</span>
              <span>{ status[ field ] }</span>
            </div>
          ))
        }
      </div>
    );
  }
}

export default DisplayStatus;
